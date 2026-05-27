#!/usr/bin/env python3
"""
claude-ctx-watch — sidecar that watches a Claude Code session's transcript
and writes a Haiku-generated handoff doc when context crosses a threshold.

Designed for non-technical users who hit Claude Code's auto-compact and lose
their flow. Run alongside `claude` in a second terminal pane (or backgrounded).
When ctx % crosses the threshold, the watcher prints a big banner with the
handoff path. User types `/clear` then `/resume <path>` — no compact, no
mid-thought summary, no lost work.

Usage:
    claude-ctx-watch [--cwd PATH] [--threshold 0.70] [--poll 5]

Defaults: cwd = $PWD, threshold = 70%, poll = every 5s.

Requires: ANTHROPIC_API_KEY in env.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

CTX_LIMIT = 200_000
PROJECTS_DIR = Path.home() / ".claude" / "projects"
HANDOFFS_DIR = Path.home() / ".claude" / "handoffs"
HAIKU_MODEL = "claude-haiku-4-5-20251001"


def encode_cwd(cwd: str) -> str:
    return cwd.replace("/", "-").replace(".", "-")


def latest_jsonl(cwd: str) -> Path | None:
    proj = PROJECTS_DIR / encode_cwd(cwd)
    if not proj.exists():
        return None
    sessions = sorted(proj.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
    return sessions[-1] if sessions else None


def latest_usage_tokens(jsonl: Path) -> int:
    tokens = 0
    with jsonl.open() as stream:
        for line in stream:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("type") != "assistant":
                continue
            usage = entry.get("message", {}).get("usage")
            if not usage:
                continue
            tokens = (
                usage.get("input_tokens", 0)
                + usage.get("cache_read_input_tokens", 0)
                + usage.get("cache_creation_input_tokens", 0)
            )
    return tokens


def transcript_tail(jsonl: Path, max_msgs: int = 40) -> str:
    msgs = []
    with jsonl.open() as stream:
        for line in stream:
            try:
                msgs.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    summary = []
    for entry in msgs[-max_msgs:]:
        msg = entry.get("message", {})
        role = msg.get("role") or entry.get("type", "?")
        content = msg.get("content")
        text = ""
        if isinstance(content, list):
            parts = []
            for block in content:
                btype = block.get("type")
                if btype == "text":
                    parts.append(block.get("text", "")[:600])
                elif btype == "tool_use":
                    parts.append(f"[tool: {block.get('name')}]")
                elif btype == "tool_result":
                    parts.append("[tool_result]")
            text = " ".join(parts)
        elif isinstance(content, str):
            text = content[:600]
        summary.append(f"{role}: {text[:600]}")
    return "\n".join(summary)


def git_state(cwd: str) -> str:
    import subprocess

    try:
        branch = subprocess.check_output(
            ["git", "-C", cwd, "branch", "--show-current"], text=True
        ).strip()
        status = subprocess.check_output(
            ["git", "-C", cwd, "status", "--short"], text=True
        ).strip()
        diffstat = subprocess.check_output(
            ["git", "-C", cwd, "diff", "--stat"], text=True
        ).strip()
        return f"branch: {branch}\n\nstatus:\n{status}\n\ndiff --stat:\n{diffstat}"
    except subprocess.CalledProcessError:
        return "(not a git repo)"


def haiku_handoff(api_key: str, transcript: str, git: str, cwd: str) -> str:
    prompt = f"""You are writing a Claude Code session handoff. The session
hit ~70% context and is being cleared so a fresh session can pick up. Future
Claude reads this cold — no other state survives.

CWD: {cwd}

GIT STATE:
{git}

LAST MESSAGES (truncated):
{transcript}

Write the handoff in markdown, sections in this order:

# Handoff

## Goal
One paragraph. What is the user ultimately trying to accomplish in this session?

## State
What's been done, what files are touched, what's in-flight right now.
Be specific: file paths, function names, decisions made.

## Next
Concrete next actions on resume. Numbered list. First action should be
unambiguous — the resuming Claude should know exactly what to do first.

## Gotchas
Blockers, dead-ends already ruled out, things to NOT redo, context that
isn't obvious from the code.

Hard rules:
- No fluff, no preamble, no "I'll write..." — just the doc.
- Under 400 lines.
- File paths absolute when known.
- Quote exact error messages if any appeared."""

    body = json.dumps(
        {
            "model": HAIKU_MODEL,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }
    ).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        data = json.loads(resp.read())
    return data["content"][0]["text"]


def banner(path: Path, pct: float) -> None:
    bar = "=" * 64
    msg = f"""
{bar}
  CONTEXT AT {pct:.0%} — HANDOFF READY (no compact needed)
{bar}

  Doc:  {path}

  Next:
    1. type  /clear
    2. type  /resume {path}

  Future-Claude reads the doc cold. No state lost.
{bar}
"""
    sys.stderr.write(msg)
    sys.stderr.flush()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--threshold", type=float, default=0.70)
    parser.add_argument("--poll", type=float, default=5.0)
    parser.add_argument(
        "--ctx-limit",
        type=int,
        default=CTX_LIMIT,
        help="effective context window in tokens (default 200000)",
    )
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.stderr.write("ANTHROPIC_API_KEY not set\n")
        return 1

    HANDOFFS_DIR.mkdir(parents=True, exist_ok=True)
    fired_for: set[str] = set()

    sys.stderr.write(
        f"watching cwd={args.cwd}\nthreshold={args.threshold:.0%}  poll={args.poll}s\n\n"
    )
    sys.stderr.flush()

    while True:
        try:
            jsonl = latest_jsonl(args.cwd)
            if not jsonl:
                time.sleep(args.poll)
                continue

            tokens = latest_usage_tokens(jsonl)
            pct = tokens / args.ctx_limit if args.ctx_limit else 0.0
            session = jsonl.stem
            sys.stderr.write(
                f"[{time.strftime('%H:%M:%S')}] {session[:8]}  {tokens:>7} tok  {pct:.0%}\n"
            )
            sys.stderr.flush()

            already_fired = session in fired_for
            crossed = pct >= args.threshold
            if crossed and not already_fired:
                fired_for.add(session)
                transcript = transcript_tail(jsonl)
                git = git_state(args.cwd)
                doc = haiku_handoff(api_key, transcript, git, args.cwd)
                stamp = time.strftime("%Y-%m-%d-%H%M", time.gmtime())
                out_path = HANDOFFS_DIR / f"{stamp}-haiku-{session[:8]}.md"
                out_path.write_text(doc)
                banner(out_path, pct)

            time.sleep(args.poll)
        except KeyboardInterrupt:
            sys.stderr.write("\nbye\n")
            return 0
        except Exception as err:  # noqa: BLE001
            sys.stderr.write(f"err: {err}\n")
            time.sleep(args.poll)


if __name__ == "__main__":
    raise SystemExit(main())
