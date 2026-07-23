#!/usr/bin/env python3
"""Thin Pocket (heypocketai) Public API client — mirrors granola.py / linear-gql.py.

Auth: resolves POCKET_API_KEY from env, then ~/.claude/.env, then ~/.pi/.env.
Bearer auth. Base: https://public.heypocketai.com/api/v1.

Subcommands
  recordings           List recordings (page-paginated to exhaustion).
                       --date YYYY-MM-DD (single day) OR --start / --end
                       (YYYY-MM-DD, UTC). --today = --date <today, pass via env>.
                       --tag-ids a,b  --limit N (cap total). Prints JSON array of
                       list-shaped recordings (id/title/state/recording_at/...).
  recording <id>       Full detail (GET /public/recordings/{id}): transcript,
                       raw_transcript, summarizations.
  digest               recordings --detail, emits a markdown digest (title + date
                       + v2 summary markdown) per COMPLETED recording. Use for
                       "mine my day's meetings".
  actions              Extract action items (v2.actionItems.actions) across the
                       window as JSON — assignee/label/context/dueDate/completed.
  raw <path>           GET an arbitrary API path (escape hatch, e.g. semantic
                       search once you've confirmed its POST body separately).

List response: {data:[...], pagination:{page,limit,total,total_pages,has_more},
success, error}. Page-based: increment `page` until has_more is false.
Only state=="completed" recordings carry transcript + summarizations.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://public.heypocketai.com/api/v1"


def load_api_key():
    if os.environ.get("POCKET_API_KEY"):
        return os.environ["POCKET_API_KEY"]
    for path in (os.path.expanduser("~/.claude/.env"), os.path.expanduser("~/.pi/.env")):
        try:
            with open(path) as fh:
                for line in fh:
                    line = line.strip()
                    if line.startswith("POCKET_API_KEY="):
                        return line.split("=", 1)[1].strip().strip("'\"")
        except FileNotFoundError:
            continue
    print("POCKET_API_KEY not found (env, ~/.claude/.env, ~/.pi/.env)", file=sys.stderr)
    sys.exit(2)


def api_get(path, key):
    url = path if path.startswith("http") else f"{BASE_URL}{path}"
    req = urllib.request.Request(
        url, headers={"authorization": f"Bearer {key}", "accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as err:
        body = err.read()[:400].decode("utf-8", "replace")
        print(f"HTTP {err.code} on {url}: {body}", file=sys.stderr)
        raise


def list_recordings(key, start=None, end=None, tag_ids=None, limit=None):
    recordings = []
    page = 1
    while True:
        params = {"page": page, "limit": 100}
        if start:
            params["start_date"] = start
        if end:
            params["end_date"] = end
        if tag_ids:
            params["tag_ids"] = tag_ids
        qs = urllib.parse.urlencode(params)
        resp = api_get(f"/public/recordings?{qs}", key)
        batch = resp.get("data") or []
        recordings.extend(batch)
        if limit and len(recordings) >= limit:
            return recordings[:limit]
        pg = resp.get("pagination") or {}
        if not pg.get("has_more"):
            break
        page += 1
    return recordings


def summary_markdown(detail):
    for summ in (detail.get("summarizations") or {}).values():
        md = (((summ.get("v2") or {}).get("summary") or {}).get("markdown"))
        if md:
            return md
    return None


def action_items(detail):
    out = []
    for summ in (detail.get("summarizations") or {}).values():
        for a in (((summ.get("v2") or {}).get("actionItems") or {}).get("actions") or []):
            out.append(
                {
                    "assignee": a.get("assignee"),
                    "label": a.get("label"),
                    "context": a.get("context"),
                    "dueDate": a.get("dueDate"),
                    "completed": a.get("isCompleted") or a.get("is_completed"),
                }
            )
    return out


def main():
    parser = argparse.ArgumentParser(description="Pocket (heypocketai) Public API client")
    sub = parser.add_subparsers(dest="cmd", required=True)

    def add_window(p):
        p.add_argument("--date", help="single UTC day YYYY-MM-DD (sets start=end)")
        p.add_argument("--today", help="today's date as YYYY-MM-DD (compute in shell, pass in)")
        p.add_argument("--start", help="start_date YYYY-MM-DD (UTC)")
        p.add_argument("--end", help="end_date YYYY-MM-DD (UTC)")
        p.add_argument("--tag-ids", help="comma-separated tag ids")
        p.add_argument("--limit", type=int, default=None)

    p_rec = sub.add_parser("recordings", help="list recordings")
    add_window(p_rec)
    p_rec.add_argument("--detail", action="store_true", help="fetch full detail per recording")

    p_one = sub.add_parser("recording", help="one recording detail")
    p_one.add_argument("id")

    p_dig = sub.add_parser("digest", help="markdown digest of completed recordings")
    add_window(p_dig)

    p_act = sub.add_parser("actions", help="extract action items across the window")
    add_window(p_act)

    p_raw = sub.add_parser("raw", help="GET an arbitrary API path")
    p_raw.add_argument("path")

    args = parser.parse_args()
    key = load_api_key()

    if args.cmd == "recording":
        print(json.dumps(api_get(f"/public/recordings/{args.id}", key), indent=2, default=str))
        return
    if args.cmd == "raw":
        print(json.dumps(api_get(args.path, key), indent=2, default=str))
        return

    day = getattr(args, "date", None) or getattr(args, "today", None)
    start = day or args.start
    end = day or args.end
    recs = list_recordings(key, start, end, args.tag_ids, args.limit)

    if args.cmd == "recordings":
        if args.detail:
            recs = [api_get(f"/public/recordings/{r['id']}", key).get("data", {}) for r in recs]
        print(json.dumps(recs, indent=2, default=str))
        return

    details = [api_get(f"/public/recordings/{r['id']}", key).get("data", {}) for r in recs]
    details = [d for d in details if d.get("state") == "completed"]
    details.sort(key=lambda d: d.get("recording_at") or "")

    if args.cmd == "digest":
        for d in details:
            md = summary_markdown(d) or "(no summary yet)"
            title = d.get("title") or "(untitled)"
            print(f"\n\n===== {(d.get('recording_at') or '')[:10]} | {title} =====\n{md.strip()}")
        return

    if args.cmd == "actions":
        rollup = []
        for d in details:
            for item in action_items(d):
                item["recording"] = d.get("title")
                item["recording_at"] = d.get("recording_at")
                rollup.append(item)
        print(json.dumps(rollup, indent=2, default=str))
        return


if __name__ == "__main__":
    main()
