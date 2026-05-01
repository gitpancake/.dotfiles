#!/usr/bin/env python3
"""Watch a git repo's main branch for new commits, write reactive state.

Reads config from $ART_WATCHER_CONFIG (default:
~/.dotfiles/scripts/commit-watcher.config.local — gitignored).
Writes shared state to $ART_STATE_FILE (default:
~/.local/share/art/state.json), which matrix.py polls.

Config schema (JSON):
{
  "repo_path": "/abs/path/to/repo",
  "branch": "main",
  "remote": "origin",
  "poll_seconds": 30,
  "describer_enabled": false,
  "describer_model": "claude-haiku-4-5-20251001",
  "path_palette_rules": [
    {"prefix": "src/server/",    "palette": "green"},
    {"prefix": "src/app/",       "palette": "magenta"},
    {"prefix": "src/schemas/",   "palette": "amber"},
    {"prefix": "infrastructure/", "palette": "red"},
    {"prefix": "",                "palette": "cyan"}
  ]
}

State schema (written atomically):
{
  "sha": "abc123",
  "ts": 1735689600.0,
  "burst_ts": 1735689600.0,
  "intensity": 1.4,
  "palette": "green",
  "message": "TEAM-1234 short subject",
  "files_touched": ["src/server/foo.ts"],
  "recent": [{"sha": "...", "palette": "green", "subject": "..."}]
}
"""

import fcntl
import json
import os
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_CONFIG_PATH = os.environ.get(
    "ART_WATCHER_CONFIG",
    os.path.expanduser("~/.dotfiles/scripts/commit-watcher.config.local"),
)
DEFAULT_STATE_PATH = os.environ.get(
    "ART_STATE_FILE",
    os.path.expanduser("~/.local/share/art/state.json"),
)
LOCK_PATH = os.path.expanduser("~/.local/share/art/commit-watcher.lock")
DESCRIBER_CACHE_DIR = os.path.expanduser("~/.local/share/art/describer-cache")
RECENT_RING_SIZE = 8
INTENSITY_BASELINE = 1.0
INTENSITY_DECAY_PER_TICK = 0.05
LOC_INTENSITY_SCALE = 200.0  # LOC delta that maps to +1.0 intensity bump


def acquire_singleton_lock():
    """Hold an exclusive flock on LOCK_PATH for process lifetime.

    If another watcher already holds the lock, exit cleanly (rather than
    error) so callers like the zsh `art matrix` wrapper can blindly spawn
    without checking pgrep first.

    Returns the open file handle — caller must keep a reference to it so
    the OS doesn't close it and release the lock.
    """
    Path(os.path.dirname(LOCK_PATH)).mkdir(parents=True, exist_ok=True)
    f = open(LOCK_PATH, "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.stderr.write(
            f"commit-watcher: another instance holds {LOCK_PATH}, exiting\n"
        )
        sys.exit(0)
    f.write(f"{os.getpid()}\n")
    f.flush()
    return f


def load_config(path):
    if not os.path.exists(path):
        sys.stderr.write(
            f"commit-watcher: config not found at {path}\n"
            f"Create it (gitignored) — see commit-watcher.config.example.json\n"
        )
        sys.exit(1)
    with open(path, "r") as f:
        return json.load(f)


def run_git(repo_path, *args):
    result = subprocess.run(
        ["git", "-C", repo_path, *args],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def fetch(repo_path, remote):
    subprocess.run(
        ["git", "-C", repo_path, "fetch", "--quiet", remote],
        capture_output=True, check=False,
    )


def head_sha(repo_path, remote, branch):
    return run_git(repo_path, "rev-parse", f"{remote}/{branch}")


def commits_since(repo_path, remote, branch, minutes):
    """Returns list of SHAs on remote/branch from oldest→newest within window."""
    out = run_git(
        repo_path, "log", f"{remote}/{branch}",
        f"--since={minutes} minutes ago",
        "--format=%H", "--reverse",
    )
    if not out:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def commit_subject(repo_path, sha):
    return run_git(repo_path, "log", "-1", "--format=%s", sha) or ""


def commit_files(repo_path, sha):
    out = run_git(repo_path, "show", "--stat", "--format=", "--name-only", sha)
    if not out:
        return []
    return [line for line in out.splitlines() if line.strip()]


def commit_loc_delta(repo_path, sha):
    """Returns total lines added + deleted across the commit."""
    out = run_git(repo_path, "show", "--numstat", "--format=", sha)
    if not out:
        return 0
    total = 0
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        try:
            total += int(parts[0]) + int(parts[1])
        except ValueError:
            continue  # binary files report '-'
    return total


def palette_for_files(files, rules):
    """First matching rule wins. Empty prefix is the catch-all default."""
    for f in files:
        for rule in rules:
            if f.startswith(rule.get("prefix", "")):
                return rule.get("palette", "green")
    return "green"


def describe_commit(sha, subject, files, loc_delta, model):
    """Optional Haiku call → poetic 1-liner. Cached by sha to disk.

    Falls back silently to subject if API unavailable.
    """
    cache_path = Path(DESCRIBER_CACHE_DIR) / f"{sha}.txt"
    if cache_path.exists():
        return cache_path.read_text().strip()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return subject

    try:
        import urllib.request
        import urllib.error
    except ImportError:
        return subject

    prompt = (
        f"Commit subject: {subject}\n"
        f"Files: {', '.join(files[:10])}\n"
        f"LOC delta: {loc_delta}\n\n"
        "Describe this commit in one short poetic line, max 12 words. "
        "No filler. Just the line."
    )
    body = json.dumps({
        "model": model,
        "max_tokens": 60,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        text = data.get("content", [{}])[0].get("text", "").strip()
        if not text:
            return subject
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(text)
        return text
    except (urllib.error.URLError, json.JSONDecodeError, KeyError, IndexError):
        return subject


def atomic_write_json(path, data):
    Path(os.path.dirname(path)).mkdir(parents=True, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def load_existing_state(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def process_commit(sha, ctx, recent):
    """Build state for a single commit and write it. Returns updated recent ring.

    ctx: dict carrying repo_path, rules, describer_*, state_path.
    """
    subject = commit_subject(ctx["repo_path"], sha)
    files = commit_files(ctx["repo_path"], sha)
    loc_delta = commit_loc_delta(ctx["repo_path"], sha)
    palette = palette_for_files(files, ctx["rules"])
    message = subject
    if ctx["describer_enabled"]:
        message = describe_commit(
            sha, subject, files, loc_delta, ctx["describer_model"],
        )

    intensity = min(3.0, INTENSITY_BASELINE + loc_delta / LOC_INTENSITY_SCALE)
    now = time.time()
    recent_entry = {"sha": sha[:8], "palette": palette, "subject": subject}
    deduped = [r for r in recent if r.get("sha") != sha[:8]]
    recent = ([recent_entry] + deduped)[:RECENT_RING_SIZE]

    atomic_write_json(ctx["state_path"], {
        "sha": sha,
        "ts": now,
        "burst_ts": now,
        "intensity": intensity,
        "palette": palette,
        "message": message,
        "files_touched": files,
        "recent": recent,
    })
    sys.stderr.write(
        f"commit-watcher: {sha[:8]} [{palette}] "
        f"intensity={intensity:.2f} loc={loc_delta} — {subject[:60]}\n"
    )
    return recent, intensity


def main():
    # Hold for process lifetime; assigning to a name keeps the FD alive.
    _lock_fd = acquire_singleton_lock()  # noqa: F841

    config_path = DEFAULT_CONFIG_PATH
    if len(sys.argv) > 1:
        config_path = sys.argv[1]
    config = load_config(config_path)

    repo_path = os.path.expanduser(config["repo_path"])
    branch = config.get("branch", "main")
    remote = config.get("remote", "origin")
    poll_seconds = int(config.get("poll_seconds", 30))
    backfill_minutes = int(config.get("backfill_minutes", 30))
    backfill_stagger_ms = int(config.get("backfill_stagger_ms", 1500))
    describer_enabled = bool(config.get("describer_enabled", False))
    describer_model = config.get("describer_model", "claude-haiku-4-5-20251001")
    rules = config.get("path_palette_rules", [{"prefix": "", "palette": "green"}])
    state_path = DEFAULT_STATE_PATH

    if not os.path.isdir(os.path.join(repo_path, ".git")):
        sys.stderr.write(f"commit-watcher: not a git repo: {repo_path}\n")
        sys.exit(1)

    state = load_existing_state(state_path)
    recent = state.get("recent", [])
    intensity = state.get("intensity", INTENSITY_BASELINE)

    ctx = {
        "repo_path": repo_path,
        "rules": rules,
        "describer_enabled": describer_enabled,
        "describer_model": describer_model,
        "state_path": state_path,
    }

    sys.stderr.write(
        f"commit-watcher: watching {repo_path} {remote}/{branch} "
        f"every {poll_seconds}s → {state_path}\n"
    )

    # Initial fetch so backfill sees latest remote state.
    fetch(repo_path, remote)

    # Backfill: replay commits from the last N minutes oldest→newest with a
    # small stagger so panes show a visible ripple of recent history on boot.
    backfill_shas = commits_since(repo_path, remote, branch, backfill_minutes)
    if backfill_shas:
        sys.stderr.write(
            f"commit-watcher: backfilling {len(backfill_shas)} commits "
            f"from last {backfill_minutes}min\n"
        )
        for sha in backfill_shas:
            recent, intensity = process_commit(sha, ctx, recent)
            time.sleep(backfill_stagger_ms / 1000.0)
        last_sha = backfill_shas[-1]
    else:
        # Nothing in the window; seed palette/recent from current HEAD so the
        # boot state isn't blank.
        head = head_sha(repo_path, remote, branch)
        if head:
            sys.stderr.write(
                f"commit-watcher: no commits in last {backfill_minutes}min; "
                f"seeding from HEAD {head[:8]}\n"
            )
            recent, intensity = process_commit(head, ctx, recent)
            last_sha = head
        else:
            last_sha = state.get("sha")

    while True:
        fetch(repo_path, remote)
        current = head_sha(repo_path, remote, branch)

        if current and current != last_sha:
            recent, intensity = process_commit(current, ctx, recent)
            last_sha = current

        else:
            # No new commit: gently decay intensity back to baseline.
            if abs(intensity - INTENSITY_BASELINE) > 0.01:
                if intensity > INTENSITY_BASELINE:
                    intensity = max(INTENSITY_BASELINE, intensity - INTENSITY_DECAY_PER_TICK)
                else:
                    intensity = min(INTENSITY_BASELINE, intensity + INTENSITY_DECAY_PER_TICK)
                existing = load_existing_state(state_path)
                existing["intensity"] = intensity
                atomic_write_json(state_path, existing)

        time.sleep(poll_seconds)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.stderr.write("\ncommit-watcher: stopped\n")
