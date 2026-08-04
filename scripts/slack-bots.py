#!/usr/bin/env python3
"""Thin Slack Web API client for the Cartage employee bots (Chuck, Kelly, Jerry).

Mirrors rootly.py / pocket.py: no MCP, no per-session tool-schema tax. Each bot
acts with its OWN xoxb- token, so "read from #channel" or "delete some of Chuck's
messages" maps to one bot's identity.

Auth: for bot NAME in {chuck,kelly,jerry}, resolves <NAME>_SLACK_BOT_TOKEN from
env, then ~/.claude/.env, then ~/.pi/.env. Bearer auth. Never echoes the token.

Bots (Cartage workspace, team T05KE9YT8HG):
  chuck  -> chuck_noland  U0B9CPT4BAN
  kelly  -> kelly_frears  U0B1MMDTC87
  jerry  -> jerry         U0B8AM7GB1S

Key constraints:
  - conversations.history needs the bot to be a MEMBER of the channel
    (else not_in_channel). Public channels: invite the bot once.
  - chat.delete only deletes messages the SAME bot authored. You cannot delete
    another bot's or a human's messages with a bot token.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://slack.com/api"

BOTS = {
    "chuck": {"env": "CHUCK_SLACK_BOT_TOKEN", "user_id": "U0B9CPT4BAN", "user": "chuck_noland"},
    "kelly": {"env": "KELLY_SLACK_BOT_TOKEN", "user_id": "U0B1MMDTC87", "user": "kelly_frears"},
    "jerry": {"env": "JERRY_SLACK_BOT_TOKEN", "user_id": "U0B8AM7GB1S", "user": "jerry"},
}


def load_token(bot):
    var = BOTS[bot]["env"]
    if os.environ.get(var):
        return os.environ[var]
    for path in (os.path.expanduser("~/.claude/.env"), os.path.expanduser("~/.pi/.env")):
        try:
            with open(path) as fh:
                for line in fh:
                    line = line.strip()
                    if line.startswith(var + "="):
                        return line.split("=", 1)[1].strip().strip("'\"")
        except FileNotFoundError:
            continue
    sys.exit(f"{var} not found (env, ~/.claude/.env, ~/.pi/.env)")


def call(bot, method, params=None, post=False):
    token = load_token(bot)
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{API}/{method}"
    if post:
        headers["Content-Type"] = "application/json; charset=utf-8"
        data = json.dumps(params or {}).encode()
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    else:
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            body = json.loads(resp.read().decode())
    except urllib.error.HTTPError as err:
        sys.exit(f"HTTP {err.code} calling {method}: {err.read().decode()[:300]}")
    if not body.get("ok"):
        sys.exit(f"Slack error on {method}: {body.get('error')}  {json.dumps(body.get('response_metadata', {}))}")
    return body


def resolve_channel(bot, ref):
    """Accept a channel id (C…/G…/D…) or a name (with or without leading #)."""
    ref = ref.strip()
    if ref[:1] in ("C", "G", "D") and " " not in ref and ref.isalnum():
        return ref
    want = ref.lstrip("#").lower()
    cursor = ""
    while True:
        params = {"types": "public_channel,private_channel", "limit": 1000}
        if cursor:
            params["cursor"] = cursor
        body = call(bot, "conversations.list", params)
        for ch in body.get("channels", []):
            if ch.get("name", "").lower() == want:
                return ch["id"]
        cursor = body.get("response_metadata", {}).get("next_cursor", "")
        if not cursor:
            break
    sys.exit(f"channel {ref!r} not found for {bot} (is the bot in it? is it archived?)")


def _print(obj):
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def cmd_whoami(a):
    _print(call(a.bot, "auth.test"))


def cmd_channels(a):
    out, cursor = [], ""
    while True:
        params = {"types": "public_channel,private_channel", "limit": 1000, "exclude_archived": True}
        if cursor:
            params["cursor"] = cursor
        body = call(a.bot, "conversations.list", params)
        for ch in body.get("channels", []):
            if a.match and a.match.lower() not in ch.get("name", "").lower():
                continue
            out.append({"id": ch["id"], "name": ch.get("name"), "is_member": ch.get("is_member"), "is_private": ch.get("is_private")})
        cursor = body.get("response_metadata", {}).get("next_cursor", "")
        if not cursor:
            break
    _print(out)


def _fetch_history(a):
    ch = resolve_channel(a.bot, a.channel)
    params = {"channel": ch, "limit": min(a.limit, 200)}
    if a.oldest:
        params["oldest"] = a.oldest
    if a.latest:
        params["latest"] = a.latest
    msgs, cursor, ch_id = [], "", ch
    while len(msgs) < a.limit:
        if cursor:
            params["cursor"] = cursor
        body = call(a.bot, "conversations.history", params)
        msgs.extend(body.get("messages", []))
        cursor = body.get("response_metadata", {}).get("next_cursor", "")
        if not cursor or not body.get("has_more"):
            break
    msgs = msgs[: a.limit]
    if getattr(a, "mine", False):
        me = BOTS[a.bot]["user_id"]
        msgs = [m for m in msgs if m.get("user") == me]
    if getattr(a, "contains", None):
        needle = a.contains.lower()
        msgs = [m for m in msgs if needle in m.get("text", "").lower()]
    return ch_id, msgs


def cmd_history(a):
    ch_id, msgs = _fetch_history(a)
    _print([{"ts": m.get("ts"), "user": m.get("user"), "text": m.get("text", "")} for m in msgs])


def cmd_find(a):
    ch_id, msgs = _fetch_history(a)
    print(f"channel {ch_id}: {len(msgs)} matching message(s)", file=sys.stderr)
    _print([{"ts": m.get("ts"), "user": m.get("user"), "text": (m.get("text", "")[:160])} for m in msgs])


def cmd_delete(a):
    ch = resolve_channel(a.bot, a.channel)
    results = []
    for ts in a.ts:
        body = call(a.bot, "chat.delete", {"channel": ch, "ts": ts}, post=True)
        results.append({"ts": ts, "deleted": body.get("ok")})
    _print(results)


def cmd_post(a):
    ch = resolve_channel(a.bot, a.channel)
    params = {"channel": ch, "text": a.text}
    if a.thread_ts:
        params["thread_ts"] = a.thread_ts
    body = call(a.bot, "chat.postMessage", params, post=True)
    _print({"ok": body.get("ok"), "ts": body.get("ts"), "channel": body.get("channel")})


def cmd_raw(a):
    params = {}
    for kv in a.data or []:
        k, _, v = kv.partition("=")
        params[k] = v
    _print(call(a.bot, a.method, params, post=a.post))


def main():
    p = argparse.ArgumentParser(description="Cartage employee-bot Slack client (chuck/kelly/jerry)")
    p.add_argument("bot", choices=sorted(BOTS), help="which bot's identity to act as")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("whoami", help="auth.test — confirm identity").set_defaults(fn=cmd_whoami)

    pc = sub.add_parser("channels", help="list channels this bot can see")
    pc.add_argument("--match", help="substring filter on channel name")
    pc.set_defaults(fn=cmd_channels)

    def add_read_args(sp):
        sp.add_argument("channel", help="#name, name, or channel id")
        sp.add_argument("--limit", type=int, default=50)
        sp.add_argument("--mine", action="store_true", help="only this bot's own messages")
        sp.add_argument("--contains", help="only messages containing this text")
        sp.add_argument("--oldest", help="unix ts lower bound")
        sp.add_argument("--latest", help="unix ts upper bound")

    ph = sub.add_parser("history", help="read channel messages (newest first)")
    add_read_args(ph)
    ph.set_defaults(fn=cmd_history)

    pf = sub.add_parser("find", help="list ts+text of matching messages (feed to delete)")
    add_read_args(pf)
    pf.set_defaults(fn=cmd_find)

    pd = sub.add_parser("delete", help="delete message(s) by ts — ONLY this bot's own messages")
    pd.add_argument("channel", help="#name, name, or channel id")
    pd.add_argument("ts", nargs="+", help="one or more message ts values")
    pd.set_defaults(fn=cmd_delete)

    pp = sub.add_parser("post", help="post a message as this bot")
    pp.add_argument("channel")
    pp.add_argument("text")
    pp.add_argument("--thread-ts", dest="thread_ts")
    pp.set_defaults(fn=cmd_post)

    pr = sub.add_parser("raw", help="call an arbitrary Web API method")
    pr.add_argument("method")
    pr.add_argument("--data", action="append", help="k=v (repeatable)")
    pr.add_argument("--post", action="store_true")
    pr.set_defaults(fn=cmd_raw)

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
