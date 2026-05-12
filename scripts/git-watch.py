#!/usr/bin/env python3
"""Watch PRs across all repos in $CODE_DIR.

Modes:
  git-watch          interactive live pane (default; q / Ctrl-C exits)
  git-watch once     one-shot render (for `watch -tcn60 git-watch once`)
  git-watch loop     auto-refresh every $GIT_WATCH_POLL seconds (no alt-screen)
  git-watch ack      mark all fresh state changes as seen

Shows your PRs with state badges: OPEN | DRAFT | MERGED | CLOSED.
When a PR's state changes between polls, it gets a green left-bar
that fades over $GIT_WATCH_NEW_WINDOW seconds.

Env:
  CODE_DIR              — repo root scan (default ~/Documents/code)
  GIT_WATCH_SINCE       — how far back for MERGED/CLOSED PRs (default "7 days ago")
  GIT_WATCH_LIMIT       — max rows printed (default 20)
  GIT_WATCH_AUTHOR      — gh --author filter (default "@me")
  GIT_WATCH_NEW_WINDOW  — seconds to mark fresh state changes (default 15)
  GIT_WATCH_BELL        — "1" to \\a on state transition (tmux pane border)
  GIT_WATCH_POLL        — seconds between gh polls in live mode (default 60)
  GIT_WATCH_STATE       — state file (default ~/.local/share/git-watch/state.json)
"""

import fcntl
import json
import os
import select
import subprocess
import sys
import termios
import time
import tty
from datetime import datetime, timezone
from pathlib import Path

CODE_DIR = Path(os.environ.get("CODE_DIR", os.path.expanduser("~/Documents/code")))
SINCE = os.environ.get("GIT_WATCH_SINCE", "7 days ago")
LIMIT = int(os.environ.get("GIT_WATCH_LIMIT", "20"))
AUTHOR = os.environ.get("GIT_WATCH_AUTHOR", "@me")
NEW_WINDOW_S = int(os.environ.get("GIT_WATCH_NEW_WINDOW", "15"))
BELL = os.environ.get("GIT_WATCH_BELL", "0") == "1"
POLL_S = float(os.environ.get("GIT_WATCH_POLL", "60"))
STATE_PATH = Path(os.environ.get(
    "GIT_WATCH_STATE",
    os.path.expanduser("~/.local/share/git-watch/state.json"),
))
LOCK_PATH = STATE_PATH.with_suffix(".lock")

FRAME_S = 0.5

DIM     = "\033[2m"
BOLD    = "\033[1m"
RESET   = "\033[0m"
RED     = "\033[31m"
GREEN   = "\033[32m"
YELLOW  = "\033[33m"
CYAN    = "\033[36m"
MAGENTA = "\033[35m"

STATE_COLORS = {
    "OPEN": GREEN,
    "DRAFT": YELLOW,
    "MERGED": MAGENTA,
    "CLOSED": RED,
}


def run(args, cwd=None, timeout=10):
    try:
        r = subprocess.run(
            args, capture_output=True, text=True, cwd=cwd,
            check=False, timeout=timeout,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""
    return r.stdout if r.returncode == 0 else ""


def parse_iso(s):
    s = s.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return 0.0


def since_seconds():
    parts = SINCE.strip().split()
    if len(parts) >= 3 and parts[-1] == "ago":
        try:
            n = int(parts[0])
        except ValueError:
            return 7 * 86400
        unit = parts[1].rstrip("s")
        return n * {"hour": 3600, "day": 86400, "week": 604800}.get(unit, 86400)
    return 7 * 86400


def collect():
    rows = []
    if not CODE_DIR.is_dir():
        return rows
    cutoff = time.time() - since_seconds()

    for repo in sorted(CODE_DIR.iterdir()):
        if not repo.is_dir() or not (repo / ".git").exists():
            continue
        text = run([
            "gh", "pr", "list",
            "--author", AUTHOR,
            "--state", "all",
            "--limit", "20",
            "--json", "number,title,state,isDraft,updatedAt,headRefName,url",
        ], cwd=str(repo), timeout=15)
        if not text:
            continue
        try:
            prs = json.loads(text)
        except json.JSONDecodeError:
            continue
        for pr in prs:
            state = pr["state"]
            if pr.get("isDraft") and state == "OPEN":
                state = "DRAFT"
            updated = parse_iso(pr.get("updatedAt", ""))
            if state in ("MERGED", "CLOSED") and updated < cutoff:
                continue
            rows.append({
                "ts": updated,
                "repo": repo.name,
                "number": pr["number"],
                "state": state,
                "title": pr["title"],
                "branch": pr.get("headRefName", ""),
                "url": pr.get("url", ""),
            })

    state_order = {"OPEN": 0, "DRAFT": 1, "MERGED": 2, "CLOSED": 3}
    rows.sort(key=lambda r: (state_order.get(r["state"], 9), -r["ts"]))
    return rows


def load_state():
    if not STATE_PATH.exists():
        return {"pr_states": {}, "fresh": []}
    try:
        with open(STATE_PATH, "r") as f:
            d = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"pr_states": {}, "fresh": []}
    d.setdefault("pr_states", {})
    d.setdefault("fresh", [])
    d.pop("main_heads", None)
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


def update_fresh(rows):
    now = time.time()
    newly_detected = 0

    def mutate():
        nonlocal newly_detected
        state = load_state()
        known = state["pr_states"]
        fresh = [
            f for f in state["fresh"]
            if now - float(f.get("first_seen_ts", 0)) < NEW_WINDOW_S
        ]
        fresh_keys = {(f["repo"], f["number"]) for f in fresh}

        for r in rows:
            key = f"{r['repo']}:{r['number']}"
            prev_state = known.get(key)
            current_state = r["state"]
            if prev_state is not None and prev_state != current_state:
                fk = (r["repo"], r["number"])
                if fk not in fresh_keys:
                    fresh.append({
                        "repo": r["repo"],
                        "number": r["number"],
                        "from": prev_state,
                        "to": current_state,
                        "first_seen_ts": now,
                    })
                    fresh_keys.add(fk)
                    newly_detected += 1
            known[key] = current_state

        state["pr_states"] = known
        state["fresh"] = fresh
        save_state(state)
        return fresh

    fresh = with_state_lock(mutate)
    first_seen = {
        (f["repo"], f["number"]): float(f["first_seen_ts"])
        for f in fresh
    }
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
    return s[:max(0, n - 1)] + "…"


def fresh_style(age_s, blink_on):
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


def state_badge(st):
    color = STATE_COLORS.get(st, "")
    dim = DIM if st == "CLOSED" else ""
    return f"{dim}{color}{st:>6}{RESET}"


def render(out, rows, first_seen, blink_on=True, cols=None):
    if not rows:
        out.write(f"{BOLD}git-watch{RESET}  {GREEN}no PRs{RESET}\n")
        return

    counts = {}
    for r in rows:
        counts[r["state"]] = counts.get(r["state"], 0) + 1

    parts = []
    for st in ("OPEN", "DRAFT", "MERGED", "CLOSED"):
        if st in counts:
            color = STATE_COLORS.get(st, "")
            parts.append(f"{color}{counts[st]} {st.lower()}{RESET}")

    out.write(f"{BOLD}git-watch{RESET}  {' · '.join(parts)}\n\n")

    shown = rows[:LIMIT]
    if cols is None:
        cols = 80
        try:
            cols = os.get_terminal_size().columns
        except OSError:
            pass

    now = time.time()
    prev_state = None
    for r in shown:
        if r["state"] != prev_state:
            if prev_state is not None:
                out.write("\n")
            color = STATE_COLORS.get(r["state"], "")
            count = counts.get(r["state"], 0)
            out.write(f" {BOLD}{color}{r['state']}{RESET} {DIM}({count}){RESET}\n")
            prev_state = r["state"]

        repo_disp = trunc(r["repo"], 18)
        num_disp = f"#{r['number']}"

        key = (r["repo"], r["number"])
        if key in first_seen:
            age = now - first_seen[key]
            bar, subj_sgr = fresh_style(age, blink_on)
        else:
            bar = " "
            subj_sgr = ""

        right_len = 2 + len(repo_disp) + 2 + len(num_disp)
        title_w = max(20, cols - 2 - 8 - right_len)
        title_disp = trunc(r["title"], title_w)

        s_open = subj_sgr
        s_close = RESET if subj_sgr else ""

        out.write(
            f"{bar}  "
            f"{s_open}{title_disp}{s_close}  "
            f"{MAGENTA}{repo_disp}{RESET}  "
            f"{DIM}{num_disp}{RESET}\n"
        )


def cmd_once():
    rows = collect()
    first_seen, newly = update_fresh(rows)
    if BELL and newly > 0:
        sys.stdout.write("\a")
    render(sys.stdout, rows, first_seen)


def cmd_loop():
    while True:
        rows = collect()
        first_seen, newly = update_fresh(rows)
        if BELL and newly > 0:
            sys.stdout.write("\a")
        sys.stdout.write("\033[H\033[J")
        render(sys.stdout, rows, first_seen)
        sys.stdout.write(f"\n{DIM}poll {int(POLL_S)}s · ctrl-c quits{RESET}\n")
        sys.stdout.flush()
        time.sleep(POLL_S)


def cmd_watch():
    fd = sys.stdin.fileno()
    if not sys.stdin.isatty():
        cmd_once()
        return

    old_attr = termios.tcgetattr(fd)
    rows = []
    first_seen = {}
    last_poll = 0.0
    frame_idx = 0

    try:
        tty.setcbreak(fd)
        sys.stdout.write("\033[?25l\033[?1049h")
        sys.stdout.flush()

        while True:
            now = time.time()
            if now - last_poll >= POLL_S or last_poll == 0.0:
                rows = collect()
                first_seen, newly = update_fresh(rows)
                last_poll = now
                if BELL and newly > 0:
                    sys.stdout.write("\a")

            blink_on = (frame_idx % 2 == 0)

            try:
                term_cols, _ = os.get_terminal_size()
            except OSError:
                term_cols = 80

            buf = []
            class _Buf:
                def write(self, s): buf.append(s)
            render(_Buf(), rows, first_seen, blink_on=blink_on, cols=term_cols)
            sys.stdout.write("\033[H\033[J")
            sys.stdout.write("".join(buf))
            sys.stdout.write(
                f"\n{DIM}q quits · a acks fresh · poll {int(POLL_S)}s{RESET}\n"
            )
            sys.stdout.flush()

            r, _, _ = select.select([sys.stdin], [], [], FRAME_S)
            if r:
                ch = sys.stdin.read(1)
                if ch in ("q", "\x03", "\x04"):
                    break
                if ch == "a":
                    ack_fresh()
                    first_seen = {}
            frame_idx += 1
    finally:
        sys.stdout.write("\033[?25h\033[?1049l")
        sys.stdout.flush()
        termios.tcsetattr(fd, termios.TCSADRAIN, old_attr)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "once":
        cmd_once()
    elif cmd == "ack":
        ack_fresh()
    elif cmd == "loop":
        cmd_loop()
    elif cmd in ("", "watch", "live"):
        cmd_watch()
    else:
        sys.stderr.write(f"git-watch: unknown command {cmd!r}\n")
        sys.stderr.write("usage: git-watch [watch | once | loop | ack]\n")
        sys.exit(2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
