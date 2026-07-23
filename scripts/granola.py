#!/usr/bin/env python3
"""Thin Granola Public API client — mirrors the linear-gql.py passthrough pattern.

Auth: resolves GRANOLA_API_KEY from the environment, then ~/.claude/.env, then
~/.pi/.env. Bearer auth. Base: https://public-api.granola.ai/v1.

Subcommands
  notes            List notes (cursor-paginated to exhaustion). --since-days N
                   caps the lookback (stops paging once a note predates the cut).
                   --limit N caps note count. Prints a JSON array of list-shaped
                   notes (id/title/created_at) unless --detail is passed.
  note <id>        Fetch full detail for one note (GET /notes/{id}).
  digest           notes --detail, but emits a compact markdown digest
                   (title + created + summary_markdown per note) to stdout.
  raw <path>       GET an arbitrary API path (e.g. "/notes?cursor=abc").

Pagination contract (verified live 2026-07-13): the list response is
{notes, cursor, hasMore}; pass ?cursor=<value> for the next page; loop until
hasMore is false. The `limit` query param is IGNORED (page size ~10) and unknown
params 400 — send only `cursor`.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

BASE_URL = "https://public-api.granola.ai/v1"


def load_api_key():
    if os.environ.get("GRANOLA_API_KEY"):
        return os.environ["GRANOLA_API_KEY"]
    for path in (os.path.expanduser("~/.claude/.env"), os.path.expanduser("~/.pi/.env")):
        try:
            with open(path) as fh:
                for line in fh:
                    line = line.strip()
                    if line.startswith("GRANOLA_API_KEY="):
                        return line.split("=", 1)[1].strip().strip("'\"")
        except FileNotFoundError:
            continue
    print("GRANOLA_API_KEY not found (env, ~/.claude/.env, ~/.pi/.env)", file=sys.stderr)
    sys.exit(2)


def api_get(path, key):
    url = path if path.startswith("http") else f"{BASE_URL}{path}"
    req = urllib.request.Request(
        url, headers={"authorization": f"Bearer {key}", "accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as err:
        body = err.read()[:400].decode("utf-8", "replace")
        print(f"HTTP {err.code} on {url}: {body}", file=sys.stderr)
        raise


def parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def created_of(note):
    return note.get("created_at") or note.get("createdAt")


def list_notes(key, since_days=None, limit=None):
    cutoff = None
    if since_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
    notes = []
    cursor = None
    stop = False
    while not stop:
        page = api_get(f"/notes?cursor={cursor}" if cursor else "/notes", key)
        for note in page.get("notes", []):
            created = parse_dt(created_of(note))
            if cutoff and created and created < cutoff:
                stop = True
                continue
            notes.append(note)
            if limit and len(notes) >= limit:
                return notes
        cursor = page.get("cursor")
        if not page.get("hasMore") or not cursor:
            break
    return notes


def main():
    parser = argparse.ArgumentParser(description="Granola Public API client")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_notes = sub.add_parser("notes", help="list notes (paginated)")
    p_notes.add_argument("--since-days", type=int, default=None)
    p_notes.add_argument("--limit", type=int, default=None)
    p_notes.add_argument("--detail", action="store_true", help="fetch full detail per note")

    p_note = sub.add_parser("note", help="fetch one note detail")
    p_note.add_argument("id")

    p_digest = sub.add_parser("digest", help="markdown digest of note summaries")
    p_digest.add_argument("--since-days", type=int, default=14)
    p_digest.add_argument("--limit", type=int, default=None)

    p_raw = sub.add_parser("raw", help="GET an arbitrary API path")
    p_raw.add_argument("path")

    args = parser.parse_args()
    key = load_api_key()

    if args.cmd == "note":
        print(json.dumps(api_get(f"/notes/{args.id}", key), indent=2, default=str))
        return

    if args.cmd == "raw":
        print(json.dumps(api_get(args.path, key), indent=2, default=str))
        return

    if args.cmd == "notes":
        notes = list_notes(key, args.since_days, args.limit)
        if args.detail:
            notes = [api_get(f"/notes/{n['id']}", key) for n in notes if n.get("id")]
        print(json.dumps(notes, indent=2, default=str))
        return

    if args.cmd == "digest":
        notes = list_notes(key, args.since_days, args.limit)
        details = [api_get(f"/notes/{n['id']}", key) for n in notes if n.get("id")]
        details.sort(key=lambda d: created_of(d) or "")
        for d in details:
            md = d.get("summary_markdown") or d.get("summary_text") or "(no summary)"
            title = d.get("title") or "(untitled)"
            print(f"\n\n===== {(created_of(d) or '')[:10]} | {title} =====\n{md.strip()}")
        return


if __name__ == "__main__":
    main()
