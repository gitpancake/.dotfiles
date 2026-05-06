#!/usr/bin/env python3
"""Watch a git repo's refs (and GitHub PRs) for new events, write reactive state.

Reads config from $ART_WATCHER_CONFIG (default:
~/.dotfiles/scripts/commit-watcher.config.local — gitignored).
Writes shared state to $ART_STATE_FILE (default:
~/.local/share/art/state.json), which watch.py polls.

Tracks: commits on the configured branch, branch creates / pushes /
deletes across the remote, and (if `gh` is available and authenticated)
PullRequest + PullRequestReview events on the GitHub repo.

Config schema (JSON):
{
  "repo_path": "/abs/path/to/repo",
  "branch": "main",
  "remote": "origin",
  "poll_seconds": 30,
  "pr_poll_every_n_ticks": 5,
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
  "sha": "abc123",                    # newest commit on tracked branch
  "ts": 1735689600.0,
  "burst_ts": 1735689600.0,           # newest commit timestamp (drives renderer pulse)
  "intensity": 1.4,                   # 1.0 baseline, scaled by LOC delta
  "rate_1h": 7,                       # count of events (any type) in last 3600s
  "palette": "green",                 # palette of newest commit
  "message": "TEAM-1234 short subject",
  "files_touched": ["src/server/foo.ts"],
  "recent": [{"sha": "...", "palette": "green", "subject": "..."}],
  "events": [
    {"type": "pr_merge", "ts": ..., "sha": "abc",
     "ref": "feat/x", "actor": "alice", "subject": "...",
     "loc_delta": 142, "palette": "green",
     "glyph_seed": "ab", "author_seed": 47}
  ],
  "last_pr_event_id": "12345"
}

Event types: commit, branch_create, branch_push, branch_delete,
pr_open, pr_close, pr_merge, pr_review.
"""

import fcntl
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
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
RECENT_RING_SIZE = 30
EVENT_RING_SIZE = 20
INTENSITY_BASELINE = 1.0
INTENSITY_DECAY_PER_TICK = 0.05
LOC_INTENSITY_SCALE = 200.0  # LOC delta that maps to +1.0 intensity bump
GH_API_TIMEOUT_S = 10
RATE_WINDOW_S = 3600

EVENT_DEFAULT_PALETTE = {
    "branch_create": "cyan",
    "branch_push":   "green",
    "branch_delete": "red",
    "pr_open":       "magenta",
    "pr_close":      "amber",
    "pr_merge":      "green",
    "pr_review":     "amber",
    "commit":        "green",
}


def acquire_singleton_lock():
    """Hold an exclusive flock on LOCK_PATH for process lifetime.

    If another watcher already holds the lock, exit cleanly (rather than
    error) so callers like the zsh `art matrix` wrapper can blindly spawn
    without checking pgrep first.
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
    return f


def write_lock_metadata(lock_fd, repo_path):
    lock_fd.seek(0)
    lock_fd.truncate()
    lock_fd.write(f"{os.getpid()}\t{repo_path}\n")
    lock_fd.flush()


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
        ["git", "-C", repo_path, "fetch", "--prune", "--quiet", remote],
        capture_output=True, check=False,
    )


def head_sha(repo_path, remote, branch):
    return run_git(repo_path, "rev-parse", f"{remote}/{branch}")


def commits_since(repo_path, remote, branch, minutes):
    """List of SHAs on remote/branch from oldest→newest within window."""
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


def commit_author(repo_path, sha):
    return run_git(repo_path, "log", "-1", "--format=%an", sha) or ""


def commit_files(repo_path, sha):
    out = run_git(repo_path, "show", "--stat", "--format=", "--name-only", sha)
    if not out:
        return []
    return [line for line in out.splitlines() if line.strip()]


def commit_loc_delta(repo_path, sha):
    """Total lines added + deleted across the commit."""
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
    """Return (primary, secondary) palettes. The first matching rule for
    any file wins primary; the next distinct rule (if any) is secondary.
    Renderer can blend if it wants. Empty-prefix rule is the catch-all.
    """
    primary = None
    secondary = None
    for f in files:
        for rule in rules:
            if f.startswith(rule.get("prefix", "")):
                p = rule.get("palette", "green")
                if primary is None:
                    primary = p
                elif p != primary and secondary is None:
                    secondary = p
                break
        if primary is not None and secondary is not None:
            break
    return primary or "green", secondary or (primary or "green")


def author_seed(actor):
    if not actor:
        return 0
    return sum(ord(c) for c in actor) % 256


def make_event(event_type, ref, sha, repo_path, rules,
               actor=None, subject=None, loc_delta=None, palette=None, ts=None):
    """Build event record. Most fields auto-derive from sha via git when
    not provided (PR events pass explicit values to skip git lookups for
    refs that may not exist locally).
    """
    if sha and (subject is None or actor is None or loc_delta is None or palette is None):
        if subject is None:
            subject = commit_subject(repo_path, sha)
        if actor is None:
            actor = commit_author(repo_path, sha)
        if loc_delta is None:
            loc_delta = commit_loc_delta(repo_path, sha)
        if palette is None:
            files = commit_files(repo_path, sha)
            primary, _ = palette_for_files(files, rules)
            palette = primary
    if palette is None:
        palette = EVENT_DEFAULT_PALETTE.get(event_type, "green")
    return {
        "type": event_type,
        "ts": ts if ts is not None else time.time(),
        "sha": sha or "",
        "ref": ref or "",
        "actor": actor or "",
        "subject": subject or "",
        "loc_delta": int(loc_delta or 0),
        "palette": palette,
        "glyph_seed": (sha or "")[:2],
        "author_seed": author_seed(actor or ""),
    }


def push_events(events_list, new_events, ring_size):
    """Prepend new events (newest-first) and truncate to ring size."""
    if not new_events:
        return events_list
    return (new_events + events_list)[:ring_size]


def count_events_in_window(events, seconds):
    cutoff = time.time() - seconds
    return sum(1 for e in events if float(e.get("ts", 0)) >= cutoff)


# ----------------------------------------------------------------------
# Ref tracking (branch create / push / delete)
# ----------------------------------------------------------------------

def snapshot_refs(repo_path, remote):
    """Map of branch-short-name → sha for refs/remotes/<remote>/*, excluding HEAD."""
    out = run_git(
        repo_path, "for-each-ref",
        f"refs/remotes/{remote}/",
        "--format=%(refname:short) %(objectname)",
    )
    snapshot = {}
    if not out:
        return snapshot
    head_alias = f"{remote}/HEAD"
    for line in out.splitlines():
        parts = line.strip().split(" ", 1)
        if len(parts) != 2:
            continue
        ref, sha = parts
        if ref == head_alias:
            continue
        snapshot[ref] = sha
    return snapshot


def diff_refs(prev, curr):
    """Yields (event_type, ref, old_sha, new_sha) tuples covering creates,
    fast-forwards/force-pushes, and deletions.
    """
    out = []
    for ref, sha in curr.items():
        if ref not in prev:
            out.append(("branch_create", ref, None, sha))
        elif prev[ref] != sha:
            out.append(("branch_push", ref, prev[ref], sha))
    for ref, sha in prev.items():
        if ref not in curr:
            out.append(("branch_delete", ref, sha, None))
    return out


# ----------------------------------------------------------------------
# GitHub PR events (optional — needs `gh` cli authenticated)
# ----------------------------------------------------------------------

GITHUB_REMOTE_RE = re.compile(r"github\.com[:/]([^/]+)/([^/.\s]+)")


def github_owner_repo(repo_path, remote):
    url = run_git(repo_path, "remote", "get-url", remote)
    if not url:
        return None
    m = GITHUB_REMOTE_RE.search(url)
    if not m:
        return None
    return m.group(1), m.group(2)


def iso_to_ts(s):
    """Parse GitHub ISO8601 (`2026-05-05T12:34:56Z`) to epoch seconds."""
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc).timestamp()
    except (ValueError, TypeError):
        return time.time()


def fetch_pr_events(owner, repo, last_event_id):
    """Poll the repo events endpoint via `gh api`. Returns
    (new_event_records_newest_first, new_last_event_id). Silent on errors —
    PR reactivity is best-effort.
    """
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{owner}/{repo}/events?per_page=30"],
            capture_output=True, text=True, check=False,
            timeout=GH_API_TIMEOUT_S,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return [], last_event_id
    if result.returncode != 0:
        return [], last_event_id
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return [], last_event_id
    if not isinstance(data, list):
        return [], last_event_id

    new_records = []
    new_last = last_event_id
    for ev in data:
        ev_id = ev.get("id")
        if not ev_id:
            continue
        # GitHub events come newest-first. Stop once we hit the last seen
        # event so reruns don't reprocess history. On first run
        # (last_event_id=None) we still walk the full page so the renderer
        # gets recent context.
        if last_event_id and str(ev_id) == str(last_event_id):
            break
        if new_last is None or str(ev_id) > str(new_last):
            new_last = str(ev_id)

        ev_type = ev.get("type")
        action = ev.get("payload", {}).get("action", "")
        actor = ev.get("actor", {}).get("login", "")
        ts = iso_to_ts(ev.get("created_at"))

        record_type = None
        subject = ""
        sha = ""
        ref = ""
        loc = 0
        if ev_type == "PullRequestEvent":
            pr = ev.get("payload", {}).get("pull_request", {})
            head = pr.get("head", {})
            sha = head.get("sha", "") or ""
            ref = head.get("ref", "") or ""
            subject = pr.get("title", "")
            loc = int(pr.get("additions", 0) or 0) + int(pr.get("deletions", 0) or 0)
            if action == "opened" or action == "reopened":
                record_type = "pr_open"
            elif action == "closed":
                record_type = "pr_merge" if pr.get("merged") else "pr_close"
        elif ev_type == "PullRequestReviewEvent" and action == "submitted":
            pr = ev.get("payload", {}).get("pull_request", {})
            head = pr.get("head", {})
            sha = head.get("sha", "") or ""
            ref = head.get("ref", "") or ""
            subject = pr.get("title", "")
            record_type = "pr_review"
        if not record_type:
            continue

        new_records.append({
            "type": record_type,
            "ts": ts,
            "sha": sha,
            "ref": ref,
            "actor": actor,
            "subject": subject,
            "loc_delta": loc,
            "palette": EVENT_DEFAULT_PALETTE.get(record_type, "green"),
            "glyph_seed": (sha or "")[:2],
            "author_seed": author_seed(actor),
        })
    return new_records, new_last


# ----------------------------------------------------------------------
# Describer (optional Haiku poetic line, cached)
# ----------------------------------------------------------------------

def describe_commit(sha, subject, files, loc_delta, model):
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


# ----------------------------------------------------------------------
# State writing
# ----------------------------------------------------------------------

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


def build_commit_record(sha, ctx, recent):
    """Compute the legacy commit fields for a freshly-seen commit. Returns
    (record, new_recent_ring). Caller assembles the full state write so
    commits and ref/PR events can be batched into one atomic update.
    """
    subject = commit_subject(ctx["repo_path"], sha)
    files = commit_files(ctx["repo_path"], sha)
    loc_delta = commit_loc_delta(ctx["repo_path"], sha)
    primary_palette, secondary_palette = palette_for_files(files, ctx["rules"])
    actor = commit_author(ctx["repo_path"], sha)
    message = subject
    if ctx["describer_enabled"]:
        message = describe_commit(
            sha, subject, files, loc_delta, ctx["describer_model"],
        )
    intensity = min(3.0, INTENSITY_BASELINE + loc_delta / LOC_INTENSITY_SCALE)
    recent_entry = {"sha": sha[:8], "palette": primary_palette, "subject": subject}
    deduped = [r for r in recent if r.get("sha") != sha[:8]]
    new_recent = ([recent_entry] + deduped)[:RECENT_RING_SIZE]
    return ({
        "sha": sha,
        "subject": subject,
        "files": files,
        "loc_delta": loc_delta,
        "palette": primary_palette,
        "palette_secondary": secondary_palette,
        "message": message,
        "intensity": intensity,
        "actor": actor,
    }, new_recent)


def main():
    lock_fd = acquire_singleton_lock()  # noqa: F841 (kept alive for lock lifetime)

    config_path = DEFAULT_CONFIG_PATH
    if len(sys.argv) > 1:
        config_path = sys.argv[1]
    config = load_config(config_path)

    repo_override = os.environ.get("COMMIT_WATCHER_REPO", "").strip()
    repo_path = os.path.expanduser(repo_override or config["repo_path"])

    branch = config.get("branch", "main")
    remote = config.get("remote", "origin")
    poll_seconds = int(config.get("poll_seconds", 30))
    backfill_minutes = int(config.get("backfill_minutes", 30))
    backfill_stagger_ms = int(config.get("backfill_stagger_ms", 1500))
    pr_poll_every = max(1, int(config.get("pr_poll_every_n_ticks", 5)))
    describer_enabled = bool(config.get("describer_enabled", False))
    describer_model = config.get("describer_model", "claude-haiku-4-5-20251001")
    rules = config.get("path_palette_rules", [{"prefix": "", "palette": "green"}])
    state_path = DEFAULT_STATE_PATH

    if not os.path.isdir(os.path.join(repo_path, ".git")):
        sys.stderr.write(f"commit-watcher: not a git repo: {repo_path}\n")
        sys.exit(1)

    write_lock_metadata(lock_fd, repo_path)

    state = load_existing_state(state_path)
    recent = state.get("recent", [])
    events = state.get("events", [])
    intensity = state.get("intensity", INTENSITY_BASELINE)
    last_pr_event_id = state.get("last_pr_event_id")
    legacy = {
        "sha": state.get("sha", ""),
        "ts": state.get("ts", 0.0),
        "burst_ts": state.get("burst_ts", 0.0),
        "palette": state.get("palette", "green"),
        "palette_secondary": state.get("palette_secondary", "green"),
        "message": state.get("message", ""),
        "files_touched": state.get("files_touched", []),
    }

    ctx = {
        "repo_path": repo_path,
        "rules": rules,
        "describer_enabled": describer_enabled,
        "describer_model": describer_model,
        "state_path": state_path,
    }

    owner_repo = github_owner_repo(repo_path, remote)
    if owner_repo:
        sys.stderr.write(
            f"commit-watcher: github repo {owner_repo[0]}/{owner_repo[1]} — PR poll every {pr_poll_every} ticks\n"
        )
    else:
        sys.stderr.write("commit-watcher: non-github remote, skipping PR poll\n")

    sys.stderr.write(
        f"commit-watcher: watching {repo_path} {remote}/{branch} "
        f"every {poll_seconds}s → {state_path}\n"
    )

    fetch(repo_path, remote)
    ref_snapshot = snapshot_refs(repo_path, remote)

    backfill_shas = commits_since(repo_path, remote, branch, backfill_minutes)
    if backfill_shas:
        sys.stderr.write(
            f"commit-watcher: backfilling {len(backfill_shas)} commits "
            f"from last {backfill_minutes}min\n"
        )
        for sha in backfill_shas:
            record, recent = build_commit_record(sha, ctx, recent)
            intensity = record["intensity"]
            legacy.update({
                "sha": record["sha"],
                "ts": time.time(),
                "burst_ts": time.time(),
                "palette": record["palette"],
                "palette_secondary": record["palette_secondary"],
                "message": record["message"],
                "files_touched": record["files"],
            })
            ev = make_event(
                "commit", f"{remote}/{branch}", sha, repo_path, rules,
                actor=record["actor"], subject=record["subject"],
                loc_delta=record["loc_delta"], palette=record["palette"],
            )
            events = push_events(events, [ev], EVENT_RING_SIZE)
            time.sleep(backfill_stagger_ms / 1000.0)
        last_sha = backfill_shas[-1]
    else:
        head = head_sha(repo_path, remote, branch)
        if head:
            sys.stderr.write(
                f"commit-watcher: no commits in last {backfill_minutes}min; "
                f"seeding from HEAD {head[:8]}\n"
            )
            record, recent = build_commit_record(head, ctx, recent)
            intensity = record["intensity"]
            legacy.update({
                "sha": record["sha"],
                "ts": time.time(),
                "burst_ts": time.time(),
                "palette": record["palette"],
                "palette_secondary": record["palette_secondary"],
                "message": record["message"],
                "files_touched": record["files"],
            })
            ev = make_event(
                "commit", f"{remote}/{branch}", head, repo_path, rules,
                actor=record["actor"], subject=record["subject"],
                loc_delta=record["loc_delta"], palette=record["palette"],
            )
            events = push_events(events, [ev], EVENT_RING_SIZE)
            last_sha = head
        else:
            last_sha = state.get("sha")

    # Initial state write so renderer sees full schema immediately.
    rate_1h = count_events_in_window(events, RATE_WINDOW_S)
    atomic_write_json(state_path, {
        **legacy,
        "intensity": intensity,
        "rate_1h": rate_1h,
        "recent": recent,
        "events": events,
        "last_pr_event_id": last_pr_event_id,
    })

    tick = 0
    while True:
        time.sleep(poll_seconds)
        tick += 1

        fetch(repo_path, remote)
        new_snapshot = snapshot_refs(repo_path, remote)
        ref_events_raw = diff_refs(ref_snapshot, new_snapshot)
        ref_snapshot = new_snapshot

        new_event_records = []
        commit_event_seen = False

        # Branch-level events. Skip the tracked-branch push here — it's
        # handled below as a "commit" event with full legacy fields.
        for ev_type, ref, old_sha, new_sha in ref_events_raw:
            if ev_type == "branch_push" and ref == f"{remote}/{branch}":
                continue
            sha_for_event = new_sha or old_sha or ""
            new_event_records.append(make_event(
                ev_type, ref, sha_for_event, repo_path, rules,
            ))

        # Commit on tracked branch (legacy commit-detection path).
        current = head_sha(repo_path, remote, branch)
        if current and current != last_sha:
            record, recent = build_commit_record(current, ctx, recent)
            intensity = record["intensity"]
            now = time.time()
            legacy.update({
                "sha": record["sha"],
                "ts": now,
                "burst_ts": now,
                "palette": record["palette"],
                "palette_secondary": record["palette_secondary"],
                "message": record["message"],
                "files_touched": record["files"],
            })
            new_event_records.insert(0, make_event(
                "commit", f"{remote}/{branch}", current, repo_path, rules,
                actor=record["actor"], subject=record["subject"],
                loc_delta=record["loc_delta"], palette=record["palette"],
            ))
            last_sha = current
            commit_event_seen = True
            sys.stderr.write(
                f"commit-watcher: {current[:8]} [{record['palette']}] "
                f"intensity={intensity:.2f} loc={record['loc_delta']} — {record['subject'][:60]}\n"
            )

        # PR events every Nth tick. Best-effort; silent on failure.
        if owner_repo and tick % pr_poll_every == 0:
            pr_records, last_pr_event_id = fetch_pr_events(
                owner_repo[0], owner_repo[1], last_pr_event_id,
            )
            if pr_records:
                # Prepend in chronological order (newest first within the
                # batch is already what fetch_pr_events returns).
                new_event_records = pr_records + new_event_records
                for r in pr_records[:5]:
                    sys.stderr.write(
                        f"commit-watcher: pr event {r['type']} "
                        f"#{r['ref'] or '?'} by {r['actor']} — {r['subject'][:50]}\n"
                    )

        if new_event_records:
            events = push_events(events, new_event_records, EVENT_RING_SIZE)

        # Idle decay (only when nothing committed this tick).
        if not commit_event_seen:
            if intensity > INTENSITY_BASELINE:
                intensity = max(INTENSITY_BASELINE, intensity - INTENSITY_DECAY_PER_TICK)
            elif intensity < INTENSITY_BASELINE:
                intensity = min(INTENSITY_BASELINE, intensity + INTENSITY_DECAY_PER_TICK)

        rate_1h = count_events_in_window(events, RATE_WINDOW_S)

        existing = load_existing_state(state_path)
        rate_changed = existing.get("rate_1h") != rate_1h
        intensity_changed = abs(existing.get("intensity", 0.0) - intensity) > 0.001
        if new_event_records or rate_changed or intensity_changed:
            atomic_write_json(state_path, {
                **legacy,
                "intensity": intensity,
                "rate_1h": rate_1h,
                "recent": recent,
                "events": events,
                "last_pr_event_id": last_pr_event_id,
            })


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.stderr.write("\ncommit-watcher: stopped\n")
