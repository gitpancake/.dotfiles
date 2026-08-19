#!/usr/bin/env python3
"""Thin Rootly REST API client — mirrors pocket.py / granola.py / linear-gql.py.

Auth: resolves ROOTLY_API_KEY (a `rootly_...` token) from env, then ~/.claude/.env,
then ~/.pi/.env. Bearer auth. Base: https://api.rootly.com/v1 (JSON:API).

⚠️ Two gotchas baked in (learned live 2026-07-23):
  1. Rootly's edge WAF 403s the default python-urllib User-Agent — we always send
     a real `User-Agent`. Without it every call 403s.
  2. Rapid successive calls get rate-limited with 403/429 — we back off + retry,
     and default to a modest page size.

Subcommands
  pages                On-call pages (alerts where label source_name matches
                       ROOTLY_ALERT_SOURCE_NAME — i.e. RootlyService.createAlert).
                       Flattened + newest-first. This is the go-to: "what's
                       paged on-call for?". --since YYYY-MM-DD --status s
                       --limit N.
  alerts               ALL alerts (every source: generic_webhook, sentry, api,
                       workflow, web, slack), flattened. Same filters, plus
                       --source-name X --source Y.
  alert <short_id>     Full raw JSON:API attributes for one alert.
  incidents            List incidents (flattened: title/status/created/url).
  digest               Markdown digest of pages grouped by org, with resolve time
                       + first summary line. Use for grounding paging analysis.
  raw <path>           GET an arbitrary API path (escape hatch), e.g.
                       raw '/alerts?page%5Bsize%5D=5'.

Flattened alert fields: short_id, created_at, status, source, source_name,
urgency, resolve_minutes (ended-started, or None if open), org (parsed from a
leading [Org] in the summary), summary (data.summary, else attributes.summary),
url.

List response is JSON:API: {data:[{type,id,attributes}], meta:{current_page,
next_page,total_count,total_pages}, links:{next}}. Page-based: increment
page[number] until meta.next_page is null.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

BASE_URL = "https://api.rootly.com/v1"


def _load(var, default=None):
    if os.environ.get(var):
        return os.environ[var]
    for path in (
        os.path.expanduser("~/.claude/.env"),
        os.path.expanduser("~/.pi/.env"),
    ):
        try:
            with open(path) as fh:
                for line in fh:
                    line = line.strip()
                    if line.startswith(f"{var}="):
                        return line.split("=", 1)[1].strip().strip("'\"")
        except FileNotFoundError:
            continue
    return default


WILSON_SOURCE_NAME = _load("ROOTLY_ALERT_SOURCE_NAME")
HEADERS_BASE = {
    "Content-Type": "application/vnd.api+json",
    "Accept": "application/vnd.api+json",
    # Required: Rootly's WAF blocks the default python-urllib UA with a 403.
    "User-Agent": _load("ROOTLY_USER_AGENT", "rootly-cli/1.0"),
}


def load_api_key():
    key = _load("ROOTLY_API_KEY")
    if key:
        return key
    print(
        "ROOTLY_API_KEY not found (env, ~/.claude/.env, ~/.pi/.env)",
        file=sys.stderr,
    )
    sys.exit(2)


def api_get(path, key, tries=5):
    url = path if path.startswith("http") else f"{BASE_URL}{path}"
    headers = {**HEADERS_BASE, "Authorization": f"Bearer {key}"}
    for attempt in range(tries):
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as err:
            # 403/429 here are almost always rate limiting (the UA block is
            # handled by HEADERS_BASE) — back off and retry.
            if err.code in (403, 429) and attempt < tries - 1:
                time.sleep(1.5 * (attempt + 1))
                continue
            body = err.read()[:400].decode("utf-8", "replace")
            print(f"HTTP {err.code} on {url}: {body}", file=sys.stderr)
            raise


def paginate(path_prefix, key, page_size=25, cap=None):
    """Yield every item across pages. path_prefix carries any filters already."""
    out = []
    page = 1
    sep = "&" if "?" in path_prefix else "?"
    while True:
        path = f"{path_prefix}{sep}page%5Bnumber%5D={page}&page%5Bsize%5D={page_size}"
        resp = api_get(path, key)
        out.extend(resp.get("data") or [])
        if cap and len(out) >= cap:
            return out[:cap]
        if not (resp.get("meta") or {}).get("next_page"):
            return out
        page += 1
        time.sleep(0.8)  # stay under the rate limit


def _resolve_minutes(at):
    started, ended = at.get("started_at"), at.get("ended_at")
    if not started or not ended:
        return None
    try:
        s = datetime.fromisoformat(started)
        e = datetime.fromisoformat(ended)
        return round((e - s).total_seconds() / 60)
    except ValueError:
        return None


def flatten_alert(alert):
    at = alert.get("attributes") or {}
    source_name = next(
        (
            l.get("value")
            for l in (at.get("labels") or [])
            if l.get("key") == "source_name"
        ),
        None,
    )
    summary = ((at.get("data") or {}).get("summary")) or at.get("summary") or ""
    org = None
    m = re.match(r"\s*\[([^\]]+)\]", summary)
    if m:
        org = m.group(1)
    return {
        "short_id": at.get("short_id"),
        "created_at": at.get("created_at"),
        "status": at.get("status"),
        "source": at.get("source"),
        "source_name": source_name,
        "urgency": (at.get("alert_urgency") or {}).get("urgency"),
        "resolve_minutes": _resolve_minutes(at),
        "org": org,
        "summary": summary.replace("\n", " ").strip(),
        "url": at.get("url"),
    }


def get_alerts(key, since=None, status=None, source=None, source_name=None, cap=None):
    params = {}
    if since:
        params["filter[created_at][gte]"] = since
    if status:
        params["filter[status]"] = status
    if source:
        params["filter[source]"] = source
    prefix = "/alerts"
    if params:
        prefix += "?" + urllib.parse.urlencode(params)
    raw = paginate(prefix, key, cap=None)
    flat = [flatten_alert(a) for a in raw]
    if source_name:
        flat = [f for f in flat if f["source_name"] == source_name]
    flat.sort(key=lambda f: f.get("created_at") or "", reverse=True)
    if cap:
        flat = flat[:cap]
    return flat


def main():
    parser = argparse.ArgumentParser(description="Rootly REST API client")
    sub = parser.add_subparsers(dest="cmd", required=True)

    def add_filters(p):
        p.add_argument("--since", help="created_at >= YYYY-MM-DD (UTC)")
        p.add_argument("--status", help="triggered|acknowledged|resolved")
        p.add_argument("--limit", type=int, default=None)

    p_pages = sub.add_parser("pages", help="On-call pages (newest first)")
    add_filters(p_pages)

    p_alerts = sub.add_parser("alerts", help="all alerts (any source)")
    add_filters(p_alerts)
    p_alerts.add_argument("--source", help="generic_webhook|sentry|api|workflow|web|slack")
    p_alerts.add_argument("--source-name", help="label source_name filter")

    p_alert = sub.add_parser("alert", help="one alert full detail")
    p_alert.add_argument("short_id")

    p_inc = sub.add_parser("incidents", help="list incidents")
    add_filters(p_inc)

    p_dig = sub.add_parser("digest", help="markdown digest of pages grouped by org")
    add_filters(p_dig)

    p_raw = sub.add_parser("raw", help="GET an arbitrary API path")
    p_raw.add_argument("path")

    args = parser.parse_args()
    key = load_api_key()

    if args.cmd == "raw":
        print(json.dumps(api_get(args.path, key), indent=2, default=str))
        return

    if args.cmd == "alert":
        resp = api_get(f"/alerts?filter%5Bshort_id%5D={args.short_id}", key)
        data = resp.get("data") or []
        print(json.dumps(data[0] if data else resp, indent=2, default=str))
        return

    if args.cmd == "incidents":
        raw = paginate("/incidents", key, cap=args.limit)
        out = [
            {
                "id": i.get("id"),
                "title": (i.get("attributes") or {}).get("title"),
                "status": (i.get("attributes") or {}).get("status"),
                "created_at": (i.get("attributes") or {}).get("created_at"),
                "url": (i.get("attributes") or {}).get("url"),
            }
            for i in raw
        ]
        print(json.dumps(out, indent=2, default=str))
        return

    if args.cmd in ("pages", "digest") and not WILSON_SOURCE_NAME:
        sys.exit("ROOTLY_ALERT_SOURCE_NAME not set (env, ~/.claude/.env, ~/.pi/.env) — required for pages/digest")
    source_name = WILSON_SOURCE_NAME if args.cmd in ("pages", "digest") else getattr(args, "source_name", None)
    alerts = get_alerts(
        key,
        since=args.since,
        status=args.status,
        source=getattr(args, "source", None),
        source_name=source_name,
        cap=args.limit,
    )

    if args.cmd in ("pages", "alerts"):
        print(json.dumps(alerts, indent=2, default=str))
        return

    if args.cmd == "digest":
        by_org = {}
        for a in alerts:
            by_org.setdefault(a["org"] or "(no org)", []).append(a)
        print(f"# On-call pages — {len(alerts)} total\n")
        for org in sorted(by_org, key=lambda o: -len(by_org[o])):
            items = by_org[org]
            print(f"\n## {org} — {len(items)} page(s)")
            for a in items:
                rt = f"{a['resolve_minutes']}m" if a["resolve_minutes"] is not None else "open"
                print(f"- {(a['created_at'] or '')[:10]} | {a['status']} | resolve {rt} | {a['summary'][:140]}")
        return


if __name__ == "__main__":
    main()
