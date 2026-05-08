#!/usr/bin/env python3
"""Slack alerts → Haiku TLDR → tmux pane.

Subcommands:
  daemon       — run the Socket Mode listener (long-lived process)
  list         — print active alerts as JSON (debug)
  pane         — render active alerts for `watch` (one-shot)
  dismiss N    — dismiss the Nth active alert (1-indexed)
  dismiss-all  — clear every active alert

Config (default ~/.dotfiles/scripts/slack-tldr.config.local, override
via $SLACK_TLDR_CONFIG):
  {
    "app_token":      "xapp-…",        # Socket Mode app-level token
    "bot_token":      "xoxb-…",        # bot user OAuth token
    "channel_ids":    ["C0123"],       # empty/omitted → auto-discover via membership
    "backfill_count": 2,               # last N messages to TLDR on startup / new join
    "model":          "claude-haiku-4-5-20251001",
    "max_active":     50
  }

State at $SLACK_TLDR_STATE (default ~/.local/share/slack-tldr/state.json):
  {
    "active":        [{"id": "<ts>", "ts": <epoch>, "channel": "C…",
                       "channel_name": "alerts", "tldr": "…", "raw": "…"}],
    "dismissed_ts":  ["<ts>", …],   # ring of recent dismissals
    "channel_names": {"C…": "alerts"}  # cache for pretty rendering
  }
"""

import fcntl
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from claude_oauth import call_messages, extract_text  # noqa: E402

DEFAULT_CONFIG = os.environ.get(
    "SLACK_TLDR_CONFIG",
    os.path.expanduser("~/.dotfiles/scripts/slack-tldr.config.local"),
)
DEFAULT_STATE = os.environ.get(
    "SLACK_TLDR_STATE",
    os.path.expanduser("~/.local/share/slack-tldr/state.json"),
)
LOCK_PATH = os.path.expanduser("~/.local/share/slack-tldr/daemon.lock")
STATE_LOCK_PATH = os.path.expanduser("~/.local/share/slack-tldr/state.lock")
DEFAULT_MAX_ACTIVE = 50
DISMISSED_RING_SIZE = 500
SEEN_RING_SIZE = 200
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_BACKFILL_COUNT = 5
BACKFILL_STAGGER_MS = 500
BACKFILL_FETCH_MULTIPLIER = 8  # over-fetch then filter — joins/edits/etc can dominate
BACKFILL_FETCH_MIN = 30
BACKFILL_FETCH_MAX = 200


# ----------------------------------------------------------------------
# State helpers (CLI + daemon both call these; file-locked)
# ----------------------------------------------------------------------

def _ensure_dirs():
    Path(DEFAULT_STATE).parent.mkdir(parents=True, exist_ok=True)


def _load_state():
    _ensure_dirs()
    if not os.path.exists(DEFAULT_STATE):
        return {"active": [], "dismissed_ts": [], "channel_names": {}, "seen_ts": []}
    try:
        with open(DEFAULT_STATE, "r") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"active": [], "dismissed_ts": [], "channel_names": {}, "seen_ts": []}
    data.setdefault("active", [])
    data.setdefault("dismissed_ts", [])
    data.setdefault("channel_names", {})
    data.setdefault("seen_ts", [])
    return data


def _save_state(state):
    _ensure_dirs()
    tmp = DEFAULT_STATE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, DEFAULT_STATE)


def _with_state_lock(fn):
    """Run fn(state) → new_state under an exclusive file lock."""
    _ensure_dirs()
    lock = open(STATE_LOCK_PATH, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = _load_state()
        new_state = fn(state)
        if new_state is not None:
            _save_state(new_state)
        return new_state
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()


# ----------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------

def load_config():
    if not os.path.exists(DEFAULT_CONFIG):
        sys.stderr.write(
            f"slack-tldr: config not found at {DEFAULT_CONFIG}\n"
            f"copy slack-tldr.config.example.json and fill in tokens.\n"
        )
        sys.exit(1)
    with open(DEFAULT_CONFIG, "r") as f:
        cfg = json.load(f)
    for key in ("app_token", "bot_token"):
        if not cfg.get(key):
            sys.stderr.write(f"slack-tldr: config missing '{key}'\n")
            sys.exit(1)
    # channel_ids is optional — empty/missing means auto-discover from bot membership.
    cfg.setdefault("channel_ids", [])
    cfg.setdefault("model", DEFAULT_MODEL)
    cfg.setdefault("max_active", DEFAULT_MAX_ACTIVE)
    cfg.setdefault("backfill_count", DEFAULT_BACKFILL_COUNT)
    return cfg


# ----------------------------------------------------------------------
# Slack message text extraction + TLDR
# ----------------------------------------------------------------------

MENTION_RE = re.compile(r"<@([A-Z0-9]+)(?:\|[^>]+)?>")
CHANNEL_RE = re.compile(r"<#([A-Z0-9]+)(?:\|([^>]+))?>")
LINK_RE = re.compile(r"<(https?://[^|>]+)(?:\|([^>]+))?>")


def flatten_message_text(event):
    """Pull plain text from a Slack message event (root + attachments + blocks).
    Strips Slack-specific markup so the LLM sees clean prose.
    """
    parts = []
    if event.get("text"):
        parts.append(event["text"])
    for att in event.get("attachments", []) or []:
        for k in ("title", "pretext", "text", "fallback"):
            v = att.get(k)
            if v:
                parts.append(v)
        for f in att.get("fields", []) or []:
            title = f.get("title", "")
            value = f.get("value", "")
            if title or value:
                parts.append(f"{title}: {value}".strip(": "))
    for block in event.get("blocks", []) or []:
        text = block.get("text")
        if isinstance(text, dict) and text.get("text"):
            parts.append(text["text"])
        for field in block.get("fields", []) or []:
            if isinstance(field, dict) and field.get("text"):
                parts.append(field["text"])
    raw = "\n".join(p for p in parts if p)
    raw = MENTION_RE.sub(r"@\1", raw)
    raw = CHANNEL_RE.sub(lambda m: f"#{m.group(2) or m.group(1)}", raw)
    raw = LINK_RE.sub(lambda m: m.group(2) or m.group(1), raw)
    return raw.strip()


def haiku_tldr(text, model):
    """One-line TLDR ≤15 words. Falls back to truncated raw on auth failure."""
    snippet = text[:4000]
    prompt = (
        "Summarize this Slack alert in ONE line, max 15 words. "
        "No filler, no quotes, no trailing period. "
        "Preserve identifiers (service names, error codes, hostnames).\n\n"
        f"---\n{snippet}\n---"
    )
    response = call_messages(
        model,
        [{"role": "user", "content": prompt}],
        max_tokens=80,
        timeout=15,
    )
    out = extract_text(response).strip()
    if not out:
        return text.replace("\n", " ")[:120]
    out = out.splitlines()[0].strip().strip("\"'")
    return out[:200]


# ----------------------------------------------------------------------
# Daemon
# ----------------------------------------------------------------------

def acquire_singleton_lock():
    Path(os.path.dirname(LOCK_PATH)).mkdir(parents=True, exist_ok=True)
    lock = open(LOCK_PATH, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.stderr.write(
            f"slack-tldr: another daemon holds {LOCK_PATH}, exiting\n"
        )
        sys.exit(0)
    lock.write(f"{os.getpid()}\n")
    lock.flush()
    return lock


def get_channel_name(web_client, channel_id, cache):
    if channel_id in cache:
        return cache[channel_id]
    try:
        info = web_client.conversations_info(channel=channel_id)
        name = info.get("channel", {}).get("name") or channel_id
    except Exception:
        name = channel_id
    cache[channel_id] = name
    return name


def discover_member_channels(web_client):
    """Return set of channel IDs the bot is currently a member of.

    Each conversation type is queried independently so a missing
    optional scope (e.g. `groups:read`) doesn't block discovery of the
    types that *are* available.
    """
    ids = set()
    for kind in ("public_channel", "private_channel"):
        cursor = None
        while True:
            try:
                resp = web_client.conversations_list(
                    types=kind,
                    limit=200,
                    cursor=cursor or None,
                    exclude_archived=True,
                )
            except Exception as e:
                msg = str(e)
                if "missing_scope" in msg:
                    sys.stderr.write(
                        f"slack-tldr: skip {kind} (missing scope, "
                        "add groups:read for private channels)\n"
                    )
                else:
                    sys.stderr.write(
                        f"slack-tldr: conversations.list({kind}) failed: {e}\n"
                    )
                break
            for ch in resp.get("channels", []) or []:
                if ch.get("is_member"):
                    ids.add(ch["id"])
            cursor = (resp.get("response_metadata") or {}).get("next_cursor") or ""
            if not cursor:
                break
    return ids


def backfill_channel(web, channel_id, count, name_cache, model, max_active):
    """Pull last `count` non-trivial messages from channel and add as alerts."""
    if count <= 0:
        return
    fetch_limit = min(
        BACKFILL_FETCH_MAX,
        max(BACKFILL_FETCH_MIN, count * BACKFILL_FETCH_MULTIPLIER),
    )
    try:
        resp = web.conversations_history(channel=channel_id, limit=fetch_limit)
    except Exception as e:
        sys.stderr.write(f"slack-tldr: backfill {channel_id} failed: {e}\n")
        return
    msgs = resp.get("messages", []) or []
    name = get_channel_name(web, channel_id, name_cache)
    # API returns newest-first. Pick first `count` non-trivial, then reverse
    # so the oldest enters the active list first → newest ends at bottom.
    picked = []
    skip_subtypes = {
        "channel_join", "channel_leave",
        "message_changed", "message_deleted",
    }
    for ev in msgs:
        if ev.get("subtype") in skip_subtypes:
            continue
        text = flatten_message_text(ev)
        if not text:
            continue
        picked.append((ev.get("ts") or "", text))
        if len(picked) >= count:
            break
    sys.stderr.write(
        f"slack-tldr: backfill #{name} → {len(picked)} message(s)\n"
    )
    for ts, text in reversed(picked):
        try:
            tldr = haiku_tldr(text, model)
        except Exception as e:
            sys.stderr.write(f"slack-tldr: tldr failed: {e}\n")
            tldr = text.replace("\n", " ")[:120]
        add_alert(channel_id, name, ts, tldr, text, max_active)
        time.sleep(BACKFILL_STAGGER_MS / 1000.0)


def add_alert(channel_id, channel_name, ts, tldr, raw, max_active):
    def mutate(state):
        if ts in state.get("dismissed_ts", []):
            return None
        if ts in state.get("seen_ts", []):
            return None
        if any(a.get("id") == ts for a in state["active"]):
            return None
        entry = {
            "id": ts,
            "ts": float(ts) if ts else time.time(),
            "channel": channel_id,
            "channel_name": channel_name,
            "tldr": tldr,
            "raw": raw[:2000],
        }
        state["active"].append(entry)
        if len(state["active"]) > max_active:
            state["active"] = state["active"][-max_active:]
        state["channel_names"][channel_id] = channel_name
        state["seen_ts"] = (state.get("seen_ts", []) + [ts])[-SEEN_RING_SIZE:]
        return state
    _with_state_lock(mutate)


def run_daemon():
    try:
        from slack_sdk.socket_mode import SocketModeClient
        from slack_sdk.socket_mode.response import SocketModeResponse
        from slack_sdk.web import WebClient
    except ImportError:
        sys.stderr.write(
            "slack-tldr: slack_sdk not installed.\n"
            "  pip3 install --user slack_sdk\n"
        )
        sys.exit(1)

    cfg = load_config()
    lock_fd = acquire_singleton_lock()  # noqa: F841

    web = WebClient(token=cfg["bot_token"])
    client = SocketModeClient(app_token=cfg["app_token"], web_client=web)

    name_cache = {}
    state = _load_state()
    name_cache.update(state.get("channel_names", {}))

    # channel_set is the live allow-list. Empty config → discover from
    # membership; otherwise use the config list verbatim.
    explicit_ids = set(cfg.get("channel_ids") or [])
    if explicit_ids:
        channel_set = set(explicit_ids)
        sys.stderr.write(
            f"slack-tldr: using {len(channel_set)} configured channel(s)\n"
        )
    else:
        channel_set = discover_member_channels(web)
        sys.stderr.write(
            f"slack-tldr: discovered {len(channel_set)} member channel(s)\n"
        )

    # Backfill last N from each known channel before live listening starts.
    for ch in sorted(channel_set):
        backfill_channel(
            web, ch, cfg["backfill_count"],
            name_cache, cfg["model"], cfg["max_active"],
        )

    def handle(client_, req):
        client_.send_socket_mode_response(
            SocketModeResponse(envelope_id=req.envelope_id)
        )
        if req.type != "events_api":
            return
        event = req.payload.get("event", {}) or {}
        ev_type = event.get("type")

        # Newly invited to a channel → backfill last N if discovery mode is on.
        if ev_type == "member_joined_channel":
            joined_user = event.get("user")
            channel = event.get("channel")
            try:
                bot_id = (web.auth_test() or {}).get("user_id")
            except Exception:
                bot_id = None
            if joined_user and bot_id and joined_user == bot_id and channel:
                if not explicit_ids:
                    channel_set.add(channel)
                    sys.stderr.write(
                        f"slack-tldr: joined {channel}, backfilling\n"
                    )
                    backfill_channel(
                        web, channel, cfg["backfill_count"],
                        name_cache, cfg["model"], cfg["max_active"],
                    )
            return

        if ev_type != "message":
            return
        subtype = event.get("subtype")
        if subtype in {
            "message_changed", "message_deleted",
            "channel_join", "channel_leave",
        }:
            return
        channel = event.get("channel")
        if channel not in channel_set:
            return
        ts = event.get("ts") or ""
        text = flatten_message_text(event)
        if not text:
            return
        try:
            tldr = haiku_tldr(text, cfg["model"])
        except Exception as e:
            sys.stderr.write(f"slack-tldr: tldr failed: {e}\n")
            tldr = text.replace("\n", " ")[:120]
        channel_name = get_channel_name(web, channel, name_cache)
        sys.stderr.write(
            f"slack-tldr: +{channel_name} {ts} → {tldr[:80]}\n"
        )
        add_alert(channel, channel_name, ts, tldr, text, cfg["max_active"])

    client.socket_mode_request_listeners.append(handle)
    client.connect()

    # Block forever. SIGTERM from launchd will kill the process and the
    # singleton flock releases automatically.
    from threading import Event
    Event().wait()


# ----------------------------------------------------------------------
# CLI: list / pane / dismiss
# ----------------------------------------------------------------------

def cmd_list():
    state = _load_state()
    print(json.dumps(state.get("active", []), indent=2))


def cmd_pane():
    """One-shot render for `watch`. ANSI-colored numbered list."""
    state = _load_state()
    active = state.get("active", [])
    if not active:
        print("\033[2mno active alerts\033[0m")
        return
    for i, a in enumerate(active, 1):
        ts = a.get("ts") or 0
        hhmm = time.strftime("%H:%M", time.localtime(ts))
        ch = a.get("channel_name") or a.get("channel") or "?"
        tldr = a.get("tldr") or ""
        # [N] HH:MM #channel  tldr
        print(
            f"\033[33m[{i}]\033[0m \033[2m{hhmm}\033[0m "
            f"\033[36m#{ch}\033[0m  {tldr}"
        )


def cmd_dismiss(arg):
    try:
        idx = int(arg)
    except ValueError:
        sys.stderr.write(f"slack-tldr: dismiss expects integer, got {arg!r}\n")
        sys.exit(2)

    def mutate(state):
        active = state.get("active", [])
        if idx < 1 or idx > len(active):
            sys.stderr.write(
                f"slack-tldr: index {idx} out of range (1..{len(active)})\n"
            )
            return None
        removed = active.pop(idx - 1)
        state["dismissed_ts"] = (
            state.get("dismissed_ts", []) + [removed["id"]]
        )[-DISMISSED_RING_SIZE:]
        return state

    _with_state_lock(mutate)


def cmd_dismiss_all():
    def mutate(state):
        ids = [a["id"] for a in state.get("active", [])]
        state["active"] = []
        state["dismissed_ts"] = (
            state.get("dismissed_ts", []) + ids
        )[-DISMISSED_RING_SIZE:]
        return state

    _with_state_lock(mutate)


# ----------------------------------------------------------------------
# Entrypoint
# ----------------------------------------------------------------------

def main():
    argv = sys.argv[1:]
    if not argv:
        sys.stderr.write(
            "usage: slack-tldr {daemon|list|pane|dismiss N|dismiss-all}\n"
        )
        sys.exit(2)
    cmd = argv[0]
    if cmd == "daemon":
        run_daemon()
    elif cmd == "list":
        cmd_list()
    elif cmd == "pane":
        cmd_pane()
    elif cmd == "dismiss":
        if len(argv) < 2:
            sys.stderr.write("usage: slack-tldr dismiss <N>\n")
            sys.exit(2)
        cmd_dismiss(argv[1])
    elif cmd == "dismiss-all":
        cmd_dismiss_all()
    else:
        sys.stderr.write(f"slack-tldr: unknown command {cmd!r}\n")
        sys.exit(2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.stderr.write("\nslack-tldr: stopped\n")
