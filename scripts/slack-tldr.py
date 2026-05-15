#!/usr/bin/env python3
"""Slack alerts → tmux pane.

Subcommands:
  daemon       — run the Socket Mode listener (long-lived process)
  watch        — interactive pane: blinks new alerts, any key acks, q quits
  list         — print active alerts as JSON (debug)
  pane         — render active alerts for `watch(1)` (one-shot)
  ack          — mark all current alerts as seen (clears the blink)
  dismiss N    — dismiss the Nth active alert (1-indexed)
  dismiss-all  — clear every active alert

Config (default ~/.dotfiles/scripts/slack-tldr.config.local, override
via $SLACK_TLDR_CONFIG):
  {
    "app_token":      "xapp-…",        # Socket Mode app-level token
    "bot_token":      "xoxb-…",        # bot user OAuth token
    "channels": {                      # required — source of truth for watched channels
      "alerts":  {"name": "C_ID", …}, # alert-tab channels
      "monitor": {"name": "C_ID", …}  # monitor-tab channels
    },
    "backfill_hours": 24,              # backfill window on startup
    "max_active":     50
  }

State at $SLACK_TLDR_STATE (default ~/.local/share/slack-tldr/state.json):
  {
    "active":        [{"id": "<ts>", "ts": <epoch>, "channel": "C…",
                       "channel_name": "alerts", "sender": "alice",
                       "tldr": "…", "raw": "…"}],
    "dismissed_ts":  ["<ts>", …],   # ring of recent dismissals
    "ack_ts":        <epoch>,       # alerts with ts > ack_ts are "new"
    "channel_names": {"C…": "alerts"},  # cache for pretty rendering
    "user_names":    {"U…": "alice"}   # cache for sender column
  }
"""

import fcntl
import json
import os
import re
import sys
import time
from pathlib import Path

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
DEFAULT_ALERT_CHANNELS = ["alerts-channel-1", "alerts-channel-2", "alerts-channel-4"]
DISMISSED_RING_SIZE = 500
SEEN_RING_SIZE = 200
BACKFILL_STAGGER_MS = 500


# ----------------------------------------------------------------------
# State helpers (CLI + daemon both call these; file-locked)
# ----------------------------------------------------------------------

def _ensure_dirs():
    Path(DEFAULT_STATE).parent.mkdir(parents=True, exist_ok=True)


def _empty_state():
    return {
        "active": [],
        "dismissed_ts": [],
        "channel_names": {},
        "user_names": {},
        "subteam_names": {},
        "seen_ts": [],
    }


def _load_state():
    _ensure_dirs()
    if not os.path.exists(DEFAULT_STATE):
        return _empty_state()
    try:
        with open(DEFAULT_STATE, "r") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return _empty_state()
    data.setdefault("active", [])
    data.setdefault("dismissed_ts", [])
    data.setdefault("channel_names", {})
    data.setdefault("user_names", {})
    data.setdefault("subteam_names", {})
    data.setdefault("seen_ts", [])
    data.setdefault("ack_ts", 0.0)
    return data


def _save_state(state):
    _ensure_dirs()
    tmp = DEFAULT_STATE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, DEFAULT_STATE)


def _persist_user_cache(user_cache):
    """Fold the live user-name cache into the on-disk state so renderers
    (pane/watch) can show sender names without re-hitting users.info."""
    def mutate(state):
        existing = state.get("user_names", {}) or {}
        merged = dict(existing)
        merged.update(user_cache)
        if merged == existing:
            return None
        state["user_names"] = merged
        return state
    _with_state_lock(mutate)


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

    channels = cfg.get("channels")
    if not channels or not isinstance(channels, dict):
        sys.stderr.write(
            "slack-tldr: config missing 'channels' dict — "
            "see slack-tldr.config.example.json\n"
        )
        sys.exit(1)

    alert_map = channels.get("alerts") or {}
    monitor_map = channels.get("monitor") or {}
    cfg["_alert_names"] = list(alert_map.keys())
    cfg["_channel_ids"] = list(alert_map.values()) + list(monitor_map.values())
    cfg["_id_to_name"] = {v: k for m in (alert_map, monitor_map) for k, v in m.items()}

    cfg.setdefault("max_active", DEFAULT_MAX_ACTIVE)
    return cfg


# ----------------------------------------------------------------------
# Slack message text extraction
# ----------------------------------------------------------------------

MENTION_RE = re.compile(r"<@([A-Z0-9]+)(?:\|[^>]+)?>")
CHANNEL_RE = re.compile(r"<#([A-Z0-9]+)(?:\|([^>]+))?>")
LINK_RE = re.compile(r"<(https?://[^|>]+)(?:\|([^>]+))?>")
# Slack emoji shortcodes: `:rotating_light:`, `:+1:`, `:skin-tone-2:`.
# Anchor on letter / `+` / `-` so timestamps like `10:30:00` survive.
EMOJI_RE = re.compile(r":[a-z+\-][a-z0-9_+\-]*:")
MULTISPACE_RE = re.compile(r"  +")
# `<!subteam^SID>`, `<!subteam^SID|handle>`, `<!here>`, `<!channel>`,
# `<!everyone>`, `<!date^...|fallback>`. Catch-all for any `<!…>` tag.
SPECIAL_RE = re.compile(r"<!([^|>]+)(?:\|([^>]+))?>")


def _replace_special_tag(body, fallback, subteam_cache):
    if body in ("here", "channel", "everyone"):
        return f"@{body}"
    if body.startswith("subteam^"):
        sid = body.split("^", 1)[1]
        if fallback:
            return fallback if fallback.startswith("@") else f"@{fallback}"
        name = (subteam_cache or {}).get(sid)
        return f"@{name}" if name else f"@subteam-{sid[:6]}"
    return fallback or ""


def resolve_special_tags(text, subteam_cache=None):
    """Swap `<!subteam^…>` etc. for human-readable mentions."""
    if not text or "<!" not in text:
        return text
    return SPECIAL_RE.sub(
        lambda m: _replace_special_tag(m.group(1), m.group(2), subteam_cache),
        text,
    )


def strip_emoji_codes(text):
    """Drop `:shortcode:` emojis and collapse the whitespace they leave behind."""
    if not text or ":" not in text:
        return text
    out = EMOJI_RE.sub("", text)
    return MULTISPACE_RE.sub(" ", out)


STORED_MENTION_RE = re.compile(r"@(U[A-Z0-9]+|W[A-Z0-9]+)")


def _resolve_stored_user_mentions(text, user_cache):
    """Rewrite already-stored `@UXXX` strings using the on-disk user cache.
    Renderer-side only — no API calls, no cache mutation.
    """
    if not user_cache or "@U" not in text and "@W" not in text:
        return text
    def sub(m):
        uid = m.group(1)
        name = user_cache.get(uid)
        return f"@{name}" if name and name != uid else m.group(0)
    return STORED_MENTION_RE.sub(sub, text)


def _resolve_user_mentions(text, user_resolver):
    """Swap `<@UXXX>` / `<@UXXX|label>` for `@<resolved-name>` or `@label`."""
    def sub(m):
        uid = m.group(1)
        label = m.group(2) if m.lastindex and m.lastindex >= 2 else None
        if label:
            return f"@{label}"
        if user_resolver:
            try:
                name = user_resolver(uid)
                if name and name != uid:
                    return f"@{name}"
            except Exception:
                pass
        return f"@{uid}"

    return re.sub(r"<@([A-Z0-9]+)(?:\|([^>]+))?>", sub, text)


def flatten_message_text(event, subteam_cache=None, user_resolver=None):
    """Pull plain text from a Slack message event (root + attachments + blocks).
    Strips Slack-specific markup so the rendered text is clean prose.
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
    for f in event.get("files", []) or []:
        title = f.get("title") or f.get("name") or ""
        if title:
            parts.append(title)
    raw = "\n".join(p for p in parts if p)
    raw = _resolve_user_mentions(raw, user_resolver)
    raw = CHANNEL_RE.sub(lambda m: f"#{m.group(2) or m.group(1)}", raw)
    raw = LINK_RE.sub(lambda m: m.group(2) or m.group(1), raw)
    raw = resolve_special_tags(raw, subteam_cache)
    raw = strip_emoji_codes(raw)
    return raw.strip()


def tldr_line(text):
    """One-line digest of a Slack message — newlines flattened, truncated."""
    return text.replace("\n", " ").strip()[:120]


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


def get_user_name(web_client, user_id, cache):
    if not user_id:
        return ""
    if user_id in cache:
        return cache[user_id]
    # Only Slack user IDs (U…/W…) need an API lookup; bot/email senders
    # come pre-resolved (e.g. "Email", "GitHub") from sender_from_event.
    if not (user_id.startswith("U") or user_id.startswith("W")) or " " in user_id:
        cache[user_id] = user_id
        return user_id
    try:
        info = web_client.users_info(user=user_id)
        profile = info.get("user", {}).get("profile", {}) or {}
        name = (
            profile.get("display_name")
            or profile.get("real_name")
            or info.get("user", {}).get("name")
            or user_id
        )
    except Exception:
        name = user_id
    cache[user_id] = name
    return name


def load_usergroups(web_client):
    """Map subteam ID → handle (e.g. `S0A2QUAVDSS` → `oncall`).

    Requires `usergroups:read`. Silent on missing scope; renderer
    falls back to a short ID badge so unknown subteams stay readable.
    """
    try:
        resp = web_client.usergroups_list()
    except Exception as e:
        sys.stderr.write(
            f"slack-tldr: usergroups.list failed ({e}); "
            "add `usergroups:read` to resolve subteam mentions\n"
        )
        return {}
    out = {}
    for g in resp.get("usergroups", []) or []:
        gid = g.get("id")
        if not gid:
            continue
        out[gid] = g.get("handle") or g.get("name") or gid
    return out


def _persist_subteam_cache(subteam_cache):
    def mutate(state):
        existing = state.get("subteam_names", {}) or {}
        merged = dict(existing)
        merged.update(subteam_cache)
        if merged == existing:
            return None
        state["subteam_names"] = merged
        return state
    _with_state_lock(mutate)


def sender_from_event(event):
    """Return a display name, not an opaque ID, when possible.

    Email integrations and other bot messages set `bot_profile.name`
    (human-readable) but leave `user` empty — use that before falling
    back to `username` / `bot_id` / `user`.
    """
    bot_profile = event.get("bot_profile") or {}
    return (
        bot_profile.get("name")
        or event.get("username")
        or event.get("user")
        or event.get("bot_id")
        or ""
    )


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


SKIP_SUBTYPES = {
    "channel_join", "channel_leave",
    "message_changed", "message_deleted",
}


def _is_thread_reply(ev):
    """True for replies inside a thread — i.e. `thread_ts` is set and is
    not the message's own `ts`. Parent messages have either no `thread_ts`
    or `thread_ts == ts`.
    """
    tts = ev.get("thread_ts")
    return bool(tts) and tts != ev.get("ts")


def backfill_channel(web, channel_id, name_cache, user_cache, subteam_cache, backfill_hours, max_active):
    """Pull top-level messages from the last `backfill_hours` and add as alerts.
    Thread replies are intentionally skipped — they belong to the parent's context.
    """
    cutoff = time.time() - backfill_hours * 3600
    name = get_channel_name(web, channel_id, name_cache)
    picked = []
    cursor = None
    user_resolver = lambda uid: get_user_name(web, uid, user_cache)
    while True:
        try:
            kwargs = {
                "channel": channel_id,
                "limit": 200,
                "oldest": str(cutoff),
                "inclusive": True,
            }
            if cursor:
                kwargs["cursor"] = cursor
            resp = web.conversations_history(**kwargs)
        except Exception as e:
            sys.stderr.write(f"slack-tldr: backfill {channel_id} failed: {e}\n")
            return
        for ev in resp.get("messages", []) or []:
            if ev.get("subtype") in SKIP_SUBTYPES:
                continue
            if _is_thread_reply(ev):
                continue
            text = flatten_message_text(ev, subteam_cache, user_resolver)
            if not text:
                continue
            picked.append((ev.get("ts") or "", text, sender_from_event(ev)))
        cursor = (resp.get("response_metadata") or {}).get("next_cursor") or ""
        if not cursor:
            break
    picked.sort(key=lambda p: float(p[0] or 0))
    sys.stderr.write(
        f"slack-tldr: backfill #{name} → {len(picked)} message(s)\n"
    )
    for ts, text, sender_id in picked:
        sender = user_resolver(sender_id) if sender_id else ""
        add_alert(channel_id, name, ts, tldr_line(text), text, sender, max_active)
        time.sleep(BACKFILL_STAGGER_MS / 1000.0)


def add_alert(channel_id, channel_name, ts, tldr, raw, sender, max_active):
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
            "sender": sender or "",
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

    name_cache = dict(cfg["_id_to_name"])
    state = _load_state()
    name_cache.update(state.get("channel_names", {}))
    name_cache.update(cfg["_id_to_name"])
    user_cache = dict(state.get("user_names", {}))
    subteam_cache = dict(state.get("subteam_names", {}))
    subteam_cache.update(load_usergroups(web))
    _persist_subteam_cache(subteam_cache)

    user_resolver = lambda uid: get_user_name(web, uid, user_cache)

    channel_set = set(cfg["_channel_ids"])
    sys.stderr.write(
        f"slack-tldr: {len(channel_set)} configured channel(s)\n"
    )

    member_ids = discover_member_channels(web)
    missing = channel_set - member_ids
    if missing:
        for ch_id in sorted(missing):
            name = cfg["_id_to_name"].get(ch_id, ch_id)
            sys.stderr.write(
                f"slack-tldr: WARN — bot not a member of #{name} ({ch_id}), skipping\n"
            )
        channel_set -= missing

    # Backfill last 24h from alert channels only (monitor is live-only).
    alert_ids = set(cfg.get("channels", {}).get("alerts", {}).values())
    backfill_hours = int(cfg.get("backfill_hours") or 48)
    for ch in sorted(channel_set & alert_ids):
        backfill_channel(
            web, ch, name_cache, user_cache, subteam_cache,
            backfill_hours, cfg["max_active"],
        )
    _persist_user_cache(user_cache)

    def handle(client_, req):
        client_.send_socket_mode_response(
            SocketModeResponse(envelope_id=req.envelope_id)
        )
        if req.type != "events_api":
            return
        event = req.payload.get("event", {}) or {}
        ev_type = event.get("type")

        if ev_type == "member_joined_channel":
            return

        if ev_type != "message":
            return
        if event.get("subtype") in SKIP_SUBTYPES:
            return
        if _is_thread_reply(event):
            return
        channel = event.get("channel")
        if channel not in channel_set:
            return
        ts = event.get("ts") or ""
        text = flatten_message_text(event, subteam_cache, user_resolver)
        if not text:
            return
        tldr = tldr_line(text)
        channel_name = get_channel_name(web, channel, name_cache)
        sender_id = sender_from_event(event)
        sender = user_resolver(sender_id) if sender_id else ""
        _persist_user_cache(user_cache)
        sys.stderr.write(
            f"slack-tldr: +{channel_name} {ts} {sender or '?'} → {tldr[:80]}\n"
        )
        add_alert(channel, channel_name, ts, tldr, text, sender, cfg["max_active"])

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


BOLD  = "\033[1m"
DIM   = "\033[2m"
RESET = "\033[0m"
RED   = "\033[31m"
GREEN = "\033[32m"
CYAN  = "\033[36m"
ALERT_NEW_ON   = "\033[1;7;31m"
ALERT_NEW_OFF  = "\033[1;7;33m"


SENDER_COL_W = 10


def _fmt_sender(sender):
    if not sender:
        return ""
    if len(sender) <= SENDER_COL_W:
        return sender
    return sender[: SENDER_COL_W - 1] + "…"


def _truncate_line(s, max_cols):
    """Collapse to one line and truncate w/ ellipsis to fit terminal width."""
    one_line = s.replace("\n", " ").replace("\r", " ")
    if max_cols <= 0 or len(one_line) <= max_cols:
        return one_line
    if max_cols == 1:
        return "…"
    return one_line[: max_cols - 1] + "…"


def _render_alert_line(a, ack_ts, out, blink_on, cols, is_monitor=False):
    ts = float(a.get("ts") or 0)
    hhmm = time.strftime("%H:%M", time.localtime(ts))
    ch = a.get("channel_name") or a.get("channel") or "?"
    sender = _fmt_sender(a.get("sender") or "")
    tldr = a.get("tldr") or ""

    # Plain-text layout decides width; ANSI escapes are layered after.
    sender_col = sender.ljust(SENDER_COL_W) if sender else " " * SENDER_COL_W
    plain_prefix = f" {hhmm} #{ch}  {sender_col}  "
    budget = max(10, cols - len(plain_prefix) - 1)
    msg = _truncate_line(tldr, budget)

    if ts > ack_ts:
        if is_monitor:
            out.write(
                f"{GREEN}{hhmm} #{ch}{RESET}  "
                f"{DIM}{sender_col}{RESET}  {msg}\n"
            )
        else:
            sgr = ALERT_NEW_ON if blink_on else ALERT_NEW_OFF
            out.write(
                f"{sgr} {hhmm} #{ch}  {sender_col}  {msg} {RESET}\n"
            )
    else:
        out.write(
            f"{DIM}{hhmm}{RESET} {CYAN}#{ch}{RESET}  "
            f"{DIM}{sender_col}{RESET}  {msg}\n"
        )


def _partition_alerts(active, alert_channels):
    alert_set = set(alert_channels)
    alerts, monitor = [], []
    for a in active:
        ch = a.get("channel_name") or ""
        if ch in alert_set:
            alerts.append(a)
        else:
            monitor.append(a)
    return alerts, monitor


def _render_section_header(out, title, items, ack_ts, blink_on, show_counts=True, is_monitor=False):
    if not show_counts:
        out.write(f"{BOLD}{title}{RESET}\n")
        return
    new_count = sum(1 for a in items if float(a.get("ts") or 0) > ack_ts)
    if not items:
        out.write(f"{BOLD}{title}{RESET}  {DIM}clear{RESET}\n")
    elif new_count:
        if is_monitor:
            out.write(f"{BOLD}{title}{RESET}  {GREEN}{new_count} new{RESET} {DIM}({len(items)} total){RESET}\n")
        else:
            badge = ALERT_NEW_ON if blink_on else ALERT_NEW_OFF
            out.write(f"{BOLD}{title}{RESET}  {badge} {new_count} NEW {RESET} {DIM}({len(items)} total){RESET}\n")
    else:
        out.write(f"{BOLD}{title}{RESET}  {RED}{len(items)} active{RESET}\n")


VIEW_SPLIT   = 0
VIEW_ALERTS  = 1
VIEW_MONITOR = 2
VIEW_NAMES   = ["split", "alerts", "monitor"]
VIEW_COUNT   = 3
MONITOR_CAP_SPLIT = 2
ALERT_CAP_SPLIT = 10
SINGLE_VIEW_CAP = 14


def _render_section(out, title, items, ack_ts, blink_on, max_rows, cols, show_counts=True, is_monitor=False):
    _render_section_header(out, title, items, ack_ts, blink_on, show_counts, is_monitor=is_monitor)
    out.write("\n")
    shown = items[-max_rows:] if len(items) > max_rows else items
    if not shown:
        out.write(f"{DIM}—{RESET}\n")
    for a in shown:
        _render_alert_line(a, ack_ts, out, blink_on, cols, is_monitor=is_monitor)


def _term_size():
    try:
        ts = os.get_terminal_size()
        return ts.columns, ts.lines
    except OSError:
        return 80, 24


def _render_pane(state, out, blink_on=True, alert_channels=None, view=VIEW_SPLIT):
    active = state.get("active", [])
    ack_ts = float(state.get("ack_ts") or 0.0)
    if not active:
        out.write(f"{DIM}no active alerts{RESET}\n")
        return

    if alert_channels is None:
        alert_channels = DEFAULT_ALERT_CHANNELS

    # Clean up legacy entries written before the daemon learned to
    # resolve subteam / user IDs and strip emoji codes. Helpers short-
    # circuit when their trigger chars are absent.
    subteam_cache = state.get("subteam_names") or {}
    user_cache = state.get("user_names") or {}
    for a in active:
        tldr = a.get("tldr") or ""
        if not tldr:
            continue
        cleaned = resolve_special_tags(tldr, subteam_cache)
        cleaned = _resolve_stored_user_mentions(cleaned, user_cache)
        cleaned = strip_emoji_codes(cleaned)
        if cleaned != tldr:
            a["tldr"] = cleaned

    alerts, monitor = _partition_alerts(active, alert_channels)
    alerts.sort(key=lambda a: float(a.get("ts") or 0))
    monitor.sort(key=lambda a: float(a.get("ts") or 0))

    cols, rows = _term_size()
    usable = rows - 4  # top header + padding

    if view == VIEW_ALERTS:
        _render_section(out, "Alerts", alerts, ack_ts, blink_on, SINGLE_VIEW_CAP, cols)
    elif view == VIEW_MONITOR:
        _render_section(out, "Monitor", monitor, ack_ts, blink_on, SINGLE_VIEW_CAP, cols, is_monitor=True)
    else:
        alert_max = min(ALERT_CAP_SPLIT, max(3, usable - MONITOR_CAP_SPLIT - 4))
        _render_section(out, "Alerts", alerts, ack_ts, blink_on, alert_max, cols, show_counts=False)
        out.write("\n")
        _render_section(out, "Monitor", monitor, ack_ts, blink_on, MONITOR_CAP_SPLIT, cols, show_counts=False, is_monitor=True)


def _get_alert_channels():
    try:
        cfg = load_config()
        return cfg.get("_alert_names", DEFAULT_ALERT_CHANNELS)
    except SystemExit:
        return DEFAULT_ALERT_CHANNELS


def cmd_pane():
    """One-shot render for `watch(1)`. ANSI-colored numbered list."""
    _render_pane(_load_state(), sys.stdout, alert_channels=_get_alert_channels())


def cmd_ack():
    """Mark every active alert as acked — clears the blink."""
    def mutate(state):
        active = state.get("active", [])
        if not active:
            return None
        max_ts = max(float(a.get("ts") or 0) for a in active)
        state["ack_ts"] = max_ts
        return state
    _with_state_lock(mutate)


def cmd_watch():
    """Interactive in-pane viewer.

    Arrow keys cycle views: split ↔ alerts ↔ monitor.
    Any other key acks alerts. q/Ctrl-C/Ctrl-D exits.
    """
    import select
    import termios
    import tty

    fd = sys.stdin.fileno()
    if not sys.stdin.isatty():
        sys.stderr.write("slack-tldr: watch requires a TTY\n")
        sys.exit(2)

    old_attr = termios.tcgetattr(fd)
    frame_s = 0.5
    last_seen_max_ts = 0.0
    current_view = VIEW_SPLIT

    alert_channels = _get_alert_channels()

    def _view_tabs(blink_on):
        parts = []
        for i, name in enumerate(VIEW_NAMES):
            if i == current_view:
                parts.append(f"\033[7m {name} {RESET}")
            else:
                parts.append(f"{DIM}{name}{RESET}")
        return " ".join(parts)

    def render_frame(blink_on):
        sys.stdout.write("\033[2J\033[H")
        state = _load_state()
        active = state.get("active", [])
        ack_ts = float(state.get("ack_ts") or 0.0)

        alerts_in_frame, _ = _partition_alerts(active, alert_channels)
        new_count = sum(1 for a in alerts_in_frame if float(a.get("ts") or 0) > ack_ts)
        badge = ""
        if new_count:
            b = ALERT_NEW_ON if blink_on else ALERT_NEW_OFF
            badge = f"  {b} {new_count} NEW {RESET}"

        tabs = _view_tabs(blink_on)
        sys.stdout.write(f"{BOLD}slack{RESET}{badge}  {tabs}  {DIM}◂▸ view  any key acks  q quits{RESET}\n\n")

        _render_pane(state, sys.stdout, blink_on=blink_on,
                     alert_channels=alert_channels, view=current_view)
        sys.stdout.flush()
        return state, active, ack_ts

    def read_key():
        b = os.read(fd, 1)
        if not b:
            return ""
        ch = b.decode("utf-8", errors="replace")
        if ch == "\x1b":
            ready, _, _ = select.select([fd], [], [], 0.05)
            if ready:
                rest = os.read(fd, 2)
                seq = ch + rest.decode("utf-8", errors="replace")
                return seq
            return ch
        return ch

    try:
        tty.setcbreak(fd)
        sys.stdout.write("\033[?25l")
        sys.stdout.flush()
        frame_idx = 0
        while True:
            blink_on = (frame_idx % 2 == 0)
            state, active, ack_ts = render_frame(blink_on)

            alerts_only, _ = _partition_alerts(active, alert_channels)
            alert_max_ts = max(
                (float(a.get("ts") or 0) for a in alerts_only), default=0.0,
            )
            if (
                alert_max_ts > last_seen_max_ts
                and alert_max_ts > ack_ts
                and last_seen_max_ts > 0.0
            ):
                sys.stdout.write("\a")
                sys.stdout.flush()
            last_seen_max_ts = max(last_seen_max_ts, alert_max_ts)

            ready, _, _ = select.select([fd], [], [], frame_s)
            if ready:
                key = read_key()
                if key in ("q", "Q", "\x03", "\x04"):
                    break
                elif key in ("\x1b[C", "\x1b[D"):  # right / left arrow
                    delta = 1 if key == "\x1b[C" else -1
                    current_view = (current_view + delta) % VIEW_COUNT
                else:
                    cmd_ack()
            frame_idx += 1
    finally:
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()
        termios.tcsetattr(fd, termios.TCSADRAIN, old_attr)


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
            "usage: slack-tldr "
            "{daemon|watch|list|pane|ack|dismiss N|dismiss-all}\n"
        )
        sys.exit(2)
    cmd = argv[0]
    if cmd == "daemon":
        run_daemon()
    elif cmd == "watch":
        cmd_watch()
    elif cmd == "list":
        cmd_list()
    elif cmd == "pane":
        cmd_pane()
    elif cmd == "ack":
        cmd_ack()
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
