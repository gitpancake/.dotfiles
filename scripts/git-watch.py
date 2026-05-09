#!/usr/bin/env python3
"""Watch commits across all repos in $CODE_DIR. Slack-alerts style.

Modes:
  git-watch          interactive live pane (default; q / Ctrl-C exits)
  git-watch once     one-shot render (for `watch -tcn5 git-watch once`)
  git-watch ack      mark all current fresh-on-main commits as seen

Subtle "fresh" highlight: when origin/<main-branch> for a repo advances,
the new commits get a green left-bar + bold subject. The bar pulses for
the first second, then fades over $GIT_WATCH_NEW_WINDOW seconds.

Env:
  CODE_DIR              — repo root scan (default ~/Documents/code)
  GIT_WATCH_SINCE       — git --since window (default "24 hours ago")
  GIT_WATCH_LIMIT       — max rows printed (default 20)
  GIT_WATCH_AUTHOR      — optional --author filter
  GIT_WATCH_FETCH       — "1" to `git fetch --quiet` each repo (slow)
  GIT_WATCH_NEW_WINDOW  — seconds to mark fresh commits (default 15)
  GIT_WATCH_BELL        — "1" to `\\a` on first detection (tmux pane border)
  GIT_WATCH_POLL        — seconds between git polls in live mode (default 5)
  GIT_WATCH_STATE       — state file (default ~/.local/share/git-watch/state.json)
"""

import fcntl
import json
import os
import select
import subprocess
import sys
import termios
import textwrap
import time
import tty
from pathlib import Path

CODE_DIR = Path(os.environ.get("CODE_DIR", os.path.expanduser("~/Documents/code")))
SINCE = os.environ.get("GIT_WATCH_SINCE", "24 hours ago")
LIMIT = int(os.environ.get("GIT_WATCH_LIMIT", "20"))
AUTHOR = os.environ.get("GIT_WATCH_AUTHOR", "")
FETCH = os.environ.get("GIT_WATCH_FETCH", "0") == "1"
NEW_WINDOW_S = int(os.environ.get("GIT_WATCH_NEW_WINDOW", "15"))
BELL = os.environ.get("GIT_WATCH_BELL", "0") == "1"
POLL_S = float(os.environ.get("GIT_WATCH_POLL", "5"))
STATE_PATH = Path(os.environ.get(
    "GIT_WATCH_STATE",
    os.path.expanduser("~/.local/share/git-watch/state.json"),
))
LOCK_PATH = STATE_PATH.with_suffix(".lock")

MAIN_BRANCHES = ("main", "master", "trunk")
REMOTE = "origin"
FRAME_S = 0.5  # 2 Hz pulse

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
    """Diff each repo's main head vs stored. Returns (first_seen_map,
    newly_detected_count). first_seen_map keys = (repo, full_sha)."""
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


def ack_fresh():
    def mutate():
        state = load_state()
        state["fresh"] = []
        save_state(state)
    with_state_lock(mutate)


def trunc(s, n):
    if len(s) <= n:
        return s
    return s[: max(0, n - 1)] + "…"


def fresh_style(age_s, blink_on):
    """Return (left_bar, subject_sgr) given age + 2Hz blink frame.

    First second: pulse — alternates inverse-green ▍ vs bright green ▍.
    Up to 33% window: solid bright bar + bold subject.
    33-66%: plain bar.
    66-100%: dim bar.
    """
    if age_s < 0:
        age_s = 0
    if age_s < 1.0:
        if blink_on:
            return f"\033[7;32m▍{RESET}", BOLD
        return f"{GREEN}{BOLD}▍{RESET}", BOLD
    if age_s < NEW_WINDOW_S * 0.33:
        return f"{GREEN}{BOLD}▍{RESET}", BOLD
    if age_s < NEW_WINDOW_S * 0.66:
        return f"{GREEN}▍{RESET}", ""
    return f"{DIM}{GREEN}▍{RESET}", DIM


def render(out, rows, first_seen, blink_on=True, cols=None):
    window = SINCE.strip()
    if window.endswith(" ago"):
        window = window[: -len(" ago")]

    if not rows:
        out.write(
            f"{BOLD}git activity{RESET}  {GREEN}quiet{RESET} "
            f"{DIM}(last {window}){RESET}\n"
        )
        return

    n = len(rows)
    fresh_in_view = sum(
        1 for r in rows[:LIMIT] if (r[1], r[3]) in first_seen
    )
    fresh_tag = ""
    if fresh_in_view:
        sgr = f"\033[7;32m" if blink_on and any(
            (time.time() - first_seen[(r[1], r[3])]) < 1.0
            for r in rows[:LIMIT] if (r[1], r[3]) in first_seen
        ) else GREEN
        fresh_tag = f"  {sgr}+{fresh_in_view} fresh on main{RESET}"
    out.write(
        f"{BOLD}git activity{RESET}  {RED}{n} commits{RESET} "
        f"{DIM}(last {window}, top {min(LIMIT, n)}){RESET}{fresh_tag}\n\n"
    )

    shown = rows[:LIMIT]
    repo_w = min(max(len(r[1]) for r in shown), 24)

    if cols is None:
        cols = 80
        try:
            cols = os.get_terminal_size().columns
        except OSError:
            pass

    # column layout: "▍ HH:MM repo_w  <subject>"
    indent_len = 2 + 5 + 1 + repo_w + 2
    indent_str = " " * indent_len
    subj_w = max(30, cols - indent_len)

    now = time.time()
    for ts, repo, _short_sha, full_sha, author, subj in shown:
        hhmm = time.strftime("%H:%M", time.localtime(ts))
        repo_disp = trunc(repo, repo_w).ljust(repo_w)

        key = (repo, full_sha)
        if key in first_seen:
            age = now - first_seen[key]
            bar, subj_sgr = fresh_style(age, blink_on)
        else:
            bar = " "
            subj_sgr = ""
        subj_open = subj_sgr
        subj_close = RESET if subj_sgr else ""

        prefix = (
            f"{bar} {DIM}{hhmm}{RESET} "
            f"{MAGENTA}{repo_disp}{RESET}  "
        )

        parts = textwrap.wrap(
            subj, width=subj_w,
            break_long_words=False, break_on_hyphens=False,
        ) or [""]

        suffix_plain = f"  — {author}"
        for j, line in enumerate(parts):
            head = prefix if j == 0 else indent_str
            is_last = (j == len(parts) - 1)
            if is_last and len(line) + len(suffix_plain) <= subj_w:
                out.write(
                    f"{head}{subj_open}{line}{subj_close}"
                    f"  {DIM}— {author}{RESET}\n"
                )
            else:
                out.write(f"{head}{subj_open}{line}{subj_close}\n")
                if is_last:
                    out.write(f"{indent_str}{DIM}— {author}{RESET}\n")


def cmd_once():
    first_seen, newly = update_fresh()
    if BELL and newly > 0:
        sys.stdout.write("\a")
    rows = collect()
    render(sys.stdout, rows, first_seen)


def cmd_watch():
    """Live pane. Polls git every POLL_S; redraws every FRAME_S for pulse."""
    fd = sys.stdin.fileno()
    if not sys.stdin.isatty():
        cmd_once()
        return

    old_attr = termios.tcgetattr(fd)
    rows = []
    first_seen = {}
    last_poll = 0.0
    frame_idx = 0
    last_pulse_keys = set()  # for bell — only ring on transition into fresh

    try:
        tty.setcbreak(fd)
        sys.stdout.write("\033[?25l\033[?1049h")  # hide cursor + alt screen
        sys.stdout.flush()

        while True:
            now = time.time()
            if now - last_poll >= POLL_S or last_poll == 0.0:
                first_seen, newly = update_fresh()
                rows = collect()
                last_poll = now
                current_keys = set(first_seen.keys())
                arrived = current_keys - last_pulse_keys
                if BELL and arrived:
                    sys.stdout.write("\a")
                last_pulse_keys = current_keys

            blink_on = (frame_idx % 2 == 0)

            try:
                cols, _ = os.get_terminal_size()
            except OSError:
                cols = 80

            buf = []
            class _Buf:
                def write(self, s): buf.append(s)
            render(_Buf(), rows, first_seen, blink_on=blink_on, cols=cols)
            sys.stdout.write("\033[H\033[J")  # home + clear
            sys.stdout.write("".join(buf))
            sys.stdout.write(
                f"\n{DIM}q quits · a acks fresh · poll {int(POLL_S)}s{RESET}\n"
            )
            sys.stdout.flush()

            r, _, _ = select.select([sys.stdin], [], [], FRAME_S)
            if r:
                ch = sys.stdin.read(1)
                if ch in ("q", "\x03", "\x04"):  # q, Ctrl-C, Ctrl-D
                    break
                if ch == "a":
                    ack_fresh()
                    first_seen = {}
                    last_pulse_keys = set()
            frame_idx += 1
    finally:
        sys.stdout.write("\033[?25h\033[?1049l")  # restore cursor + main screen
        sys.stdout.flush()
        termios.tcsetattr(fd, termios.TCSADRAIN, old_attr)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "once":
        cmd_once()
    elif cmd == "ack":
        ack_fresh()
    elif cmd in ("", "watch", "live"):
        cmd_watch()
    else:
        sys.stderr.write(f"git-watch: unknown command {cmd!r}\n")
        sys.stderr.write("usage: git-watch [watch | once | ack]\n")
        sys.exit(2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
