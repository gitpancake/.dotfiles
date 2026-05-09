#!/usr/bin/env python3
"""Watch commits across all repos in $CODE_DIR. Slack-alerts style.

One-shot render — designed for `watch -tcn5 git-watch`. Walks every
top-level repo under $CODE_DIR, collects commits across all refs within
$GIT_WATCH_SINCE, renders newest-first.

Subtle "fresh" highlight: when origin/<main-branch> for a repo advances,
the new commits get a left-bar marker for $GIT_WATCH_NEW_WINDOW seconds.
First few seconds = bright bar + non-dim subject; then dims; then off.

Env:
  CODE_DIR              — repo root scan (default ~/Documents/code)
  GIT_WATCH_SINCE       — git --since window (default "24 hours ago")
  GIT_WATCH_LIMIT       — max rows printed (default 20)
  GIT_WATCH_AUTHOR      — optional --author filter
  GIT_WATCH_FETCH       — "1" to `git fetch --quiet` each repo (slow)
  GIT_WATCH_NEW_WINDOW  — seconds to mark fresh commits (default 15)
  GIT_WATCH_BELL        — "1" to `\\a` on first detection (tmux pane border)
  GIT_WATCH_STATE       — state file (default ~/.local/share/git-watch/state.json)
"""

import fcntl
import json
import os
import subprocess
import sys
import time
from pathlib import Path

CODE_DIR = Path(os.environ.get("CODE_DIR", os.path.expanduser("~/Documents/code")))
SINCE = os.environ.get("GIT_WATCH_SINCE", "24 hours ago")
LIMIT = int(os.environ.get("GIT_WATCH_LIMIT", "20"))
AUTHOR = os.environ.get("GIT_WATCH_AUTHOR", "")
FETCH = os.environ.get("GIT_WATCH_FETCH", "0") == "1"
NEW_WINDOW_S = int(os.environ.get("GIT_WATCH_NEW_WINDOW", "15"))
BELL = os.environ.get("GIT_WATCH_BELL", "0") == "1"
STATE_PATH = Path(os.environ.get(
    "GIT_WATCH_STATE",
    os.path.expanduser("~/.local/share/git-watch/state.json"),
))
LOCK_PATH = STATE_PATH.with_suffix(".lock")

MAIN_BRANCHES = ("main", "master", "trunk")
REMOTE = "origin"

DIM     = "\033[2m"
BOLD    = "\033[1m"
RESET   = "\033[0m"
RED     = "\033[31m"
GREEN   = "\033[32m"
YELLOW  = "\033[33m"
CYAN    = "\033[36m"
MAGENTA = "\033[35m"


def run(args, cwd=None, timeout=5):
    try:
        r = subprocess.run(
            args, capture_output=True, text=True, cwd=cwd,
            check=False, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return ""
    return r.stdout if r.returncode == 0 else ""


def collect():
    rows = []
    if not CODE_DIR.is_dir():
        return rows
    for repo in sorted(CODE_DIR.iterdir()):
        if not repo.is_dir():
            continue
        if not (repo / ".git").exists():
            continue
        if FETCH:
            run(["git", "fetch", "--quiet", "--all"], cwd=str(repo), timeout=10)
        args = [
            "git", "log", "--all", f"--since={SINCE}",
            "--format=%ct%x09%h%x09%H%x09%an%x09%s",
        ]
        if AUTHOR:
            args.insert(2, f"--author={AUTHOR}")
        text = run(args, cwd=str(repo))
        for line in text.splitlines():
            parts = line.split("\t", 4)
            if len(parts) < 5:
                continue
            ts_s, short_sha, full_sha, author, subj = parts
            try:
                ts = int(ts_s)
            except ValueError:
                continue
            rows.append((ts, repo.name, short_sha, full_sha, author, subj))
    rows.sort(reverse=True)
    return rows


def main_head(repo_path):
    """Return (branch, full_sha) for the repo's main-equivalent branch."""
    for b in MAIN_BRANCHES:
        sha = run(
            ["git", "rev-parse", "--verify", "--quiet", f"{REMOTE}/{b}"],
            cwd=repo_path,
        ).strip()
        if sha:
            return b, sha
    for b in MAIN_BRANCHES:
        sha = run(
            ["git", "rev-parse", "--verify", "--quiet", b],
            cwd=repo_path,
        ).strip()
        if sha:
            return b, sha
    return None, None


def commits_between(repo_path, old_sha, new_sha):
    if not old_sha or not new_sha or old_sha == new_sha:
        return []
    out = run(
        ["git", "log", f"{old_sha}..{new_sha}", "--format=%H"],
        cwd=repo_path,
    ).strip()
    return [s for s in out.splitlines() if s]


def load_state():
    if not STATE_PATH.exists():
        return {"main_heads": {}, "fresh": []}
    try:
        with open(STATE_PATH, "r") as f:
            d = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"main_heads": {}, "fresh": []}
    d.setdefault("main_heads", {})
    d.setdefault("fresh", [])
    return d


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(STATE_PATH) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, STATE_PATH)


def with_state_lock(fn):
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCK_PATH, "w") as lf:
        try:
            fcntl.flock(lf, fcntl.LOCK_EX)
        except OSError:
            pass
        return fn()


def update_fresh():
    """Diff each repo's main head vs stored. Returns set of full_shas
    currently considered fresh, plus first_seen_ts map, plus count of
    *newly detected this tick* (for bell).
    """
    now = time.time()
    newly_detected = 0

    def mutate():
        nonlocal newly_detected
        state = load_state()
        heads = state["main_heads"]
        fresh = [
            f for f in state["fresh"]
            if now - float(f.get("first_seen_ts", 0)) < NEW_WINDOW_S
        ]
        fresh_keys = {(f["repo"], f["sha"]) for f in fresh}

        if CODE_DIR.is_dir():
            for repo in sorted(CODE_DIR.iterdir()):
                if not repo.is_dir() or not (repo / ".git").exists():
                    continue
                branch, head = main_head(str(repo))
                if not head:
                    continue
                prev = heads.get(repo.name, {})
                prev_sha = prev.get("sha", "")
                if prev_sha and prev_sha != head:
                    new_shas = commits_between(str(repo), prev_sha, head)
                    for sha in new_shas:
                        key = (repo.name, sha)
                        if key in fresh_keys:
                            continue
                        fresh.append({
                            "repo": repo.name,
                            "sha": sha,
                            "branch": branch,
                            "first_seen_ts": now,
                        })
                        fresh_keys.add(key)
                        newly_detected += 1
                heads[repo.name] = {"branch": branch, "sha": head}

        state["main_heads"] = heads
        state["fresh"] = fresh
        save_state(state)
        return fresh

    fresh = with_state_lock(mutate)
    first_seen = {(f["repo"], f["sha"]): float(f["first_seen_ts"]) for f in fresh}
    return first_seen, newly_detected


def trunc(s, n):
    if len(s) <= n:
        return s
    return s[: max(0, n - 1)] + "…"


def fresh_marker(age_s):
    """Return (left_bar, subject_sgr) for given age. Fades over NEW_WINDOW_S."""
    if age_s < 0:
        age_s = 0
    if age_s < NEW_WINDOW_S * 0.33:
        return f"{GREEN}▍{RESET}", BOLD
    if age_s < NEW_WINDOW_S * 0.66:
        return f"{GREEN}▍{RESET}", ""
    return f"{DIM}{GREEN}▍{RESET}", DIM


def main():
    first_seen, newly_detected = update_fresh()
    rows = collect()

    window = SINCE.strip()
    if window.endswith(" ago"):
        window = window[: -len(" ago")]

    if not rows:
        print(
            f"{BOLD}git activity{RESET}  {GREEN}quiet{RESET} "
            f"{DIM}(last {window}){RESET}"
        )
        return

    if BELL and newly_detected > 0:
        sys.stdout.write("\a")

    n = len(rows)
    fresh_in_view = sum(
        1 for r in rows[:LIMIT] if (r[1], r[3]) in first_seen
    )
    fresh_tag = ""
    if fresh_in_view:
        fresh_tag = f"  {GREEN}+{fresh_in_view} fresh on main{RESET}"
    print(
        f"{BOLD}git activity{RESET}  {RED}{n} commits{RESET} "
        f"{DIM}(last {window}, top {min(LIMIT, n)}){RESET}{fresh_tag}"
    )
    print()

    shown = rows[:LIMIT]
    repo_w = min(max(len(r[1]) for r in shown), 24)

    cols = 80
    try:
        cols = os.get_terminal_size().columns
    except OSError:
        pass
    idx_w = len(str(len(shown))) + 2
    fixed = 2 + idx_w + 1 + 5 + 1 + repo_w + 1 + 7 + 2 + 3
    subj_max = max(20, cols - fixed)

    now = time.time()
    for i, (ts, repo, short_sha, full_sha, author, subj) in enumerate(shown, 1):
        hhmm = time.strftime("%H:%M", time.localtime(ts))
        repo_disp = trunc(repo, repo_w).ljust(repo_w)
        author_disp = trunc(author, 16)
        subj_disp = trunc(subj, subj_max - len(author_disp) - 3)

        key = (repo, full_sha)
        if key in first_seen:
            age = now - first_seen[key]
            bar, subj_sgr = fresh_marker(age)
        else:
            bar = " "
            subj_sgr = ""

        subj_open = subj_sgr
        subj_close = RESET if subj_sgr else ""

        print(
            f"{bar} {YELLOW}[{i}]{RESET} {DIM}{hhmm}{RESET} "
            f"{MAGENTA}{repo_disp}{RESET} "
            f"{DIM}{short_sha}{RESET}  {subj_open}{subj_disp}{subj_close}  "
            f"{DIM}— {author_disp}{RESET}"
        )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
