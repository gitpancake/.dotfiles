#!/usr/bin/env python3
"""Thin Ordinal (tryordinal.com) REST client — mirrors the granola.py passthrough pattern.

Auth: resolves ORDINAL_API_KEY from the environment, then ~/.claude/.env, then
~/.pi/.env. Bearer auth. Base: https://app.tryordinal.com/api/v1. API access
needs the Pro plan; keys are minted at app.tryordinal.com/settings/integrations/api.

Subcommands
  workspace                 GET /workspace — sanity check for the key.
  profiles [--channel C]    GET /profiles/scheduling — the profile ids posts publish from.
  posts [--status S] [--channel C] [--limit N]
                            GET /posts, cursor-paginated. Prints a JSON array.
  post <id>                 GET /posts/{id}.
  create                    POST /posts with a LinkedIn channel. Needs --title, --publish-at,
                            and --copy or --copy-file. --profile defaults to the only LinkedIn
                            scheduling profile. --status defaults to ForReview (a draft that
                            does NOT publish). --asset <assetId> may repeat.
  schedule <id> [--publish-at T]
                            POST /posts/{id}/schedule — makes the post go live at publishAt.
  unschedule <id>           POST /posts/{id}/unschedule.
  archive <id>              POST /posts/{id}/archive.
  update <id>               PATCH /posts/{id}; same flags as create, all optional.
  upload <file>             prepare → multipart POST → poll until ready; prints the assetId.
  raw <METHOD> <path> [--body-file F]
                            Arbitrary call, e.g. `raw GET /labels`.

--publish-at accepts an ISO datetime. A naive value ("2026-10-28 09:00") is local
time and is converted to UTC before sending.
"""
import argparse
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone

BASE_URL = "https://app.tryordinal.com/api/v1"
DRAFT_STATUS = "ForReview"


def load_api_key():
    if os.environ.get("ORDINAL_API_KEY"):
        return os.environ["ORDINAL_API_KEY"]
    for path in (os.path.expanduser("~/.claude/.env"), os.path.expanduser("~/.pi/.env")):
        try:
            with open(path) as fh:
                for line in fh:
                    line = line.strip()
                    if line.startswith("ORDINAL_API_KEY="):
                        return line.split("=", 1)[1].strip().strip("'\"")
        except FileNotFoundError:
            continue
    print("ORDINAL_API_KEY not found (env, ~/.claude/.env, ~/.pi/.env)", file=sys.stderr)
    sys.exit(2)


def api(method, path, key, body=None, query=None):
    url = path if path.startswith("http") else f"{BASE_URL}{path}"
    if query:
        url = f"{url}?{urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})}"
    payload = json.dumps(body).encode() if body is not None else None
    headers = {"authorization": f"Bearer {key}", "accept": "application/json"}
    if payload is not None:
        headers["content-type"] = "application/json"
    req = urllib.request.Request(url, data=payload, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as err:
        detail = err.read()[:600].decode("utf-8", "replace")
        print(f"HTTP {err.code} {method} {url}: {detail}", file=sys.stderr)
        sys.exit(1)


def to_utc_iso(value):
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_copy(args):
    if args.copy_file:
        with open(args.copy_file) as fh:
            return fh.read().rstrip("\n")
    return args.copy


def linkedin_profile_id(key, requested):
    if requested:
        return requested
    profiles = [p for p in api("GET", "/profiles/scheduling", key) if p.get("channel") == "LinkedIn"]
    if len(profiles) != 1:
        names = ", ".join(f"{p['id']} ({p.get('name')})" for p in profiles) or "none"
        print(f"need --profile: LinkedIn scheduling profiles = {names}", file=sys.stderr)
        sys.exit(2)
    return profiles[0]["id"]


def post_body(args, key, require_all):
    body = {}
    if args.title or require_all:
        body["title"] = args.title
    if args.publish_at or require_all:
        body["publishAt"] = to_utc_iso(args.publish_at)
    if args.status or require_all:
        body["status"] = args.status or DRAFT_STATUS
    if args.notes:
        body["notes"] = args.notes
    copy = read_copy(args)
    if copy is not None or require_all or args.asset:
        linkedin = {"profileId": linkedin_profile_id(key, args.profile)}
        if copy is not None:
            linkedin["copy"] = copy
        if args.asset:
            linkedin["assets"] = [{"assetId": a} for a in args.asset]
        body["linkedIn"] = linkedin
    return body


def cmd_posts(args, key):
    collected = []
    cursor = None
    while True:
        page = api("GET", "/posts", key, query={
            "limit": min(100, args.limit - len(collected)),
            "status": args.status, "channel": args.channel, "cursor": cursor,
        })
        posts = page.get("posts", [])
        collected.extend(posts)
        if not posts or len(collected) >= args.limit or not page.get("hasMore", False):
            break
        cursor = posts[-1]["id"]
    return collected[: args.limit]


def multipart(fields, file_field, filename, content):
    boundary = uuid.uuid4().hex
    chunks = []
    for name, value in fields.items():
        chunks.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode()
        )
    mimetype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    chunks.append(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"{file_field}\"; "
        f"filename=\"{filename}\"\r\nContent-Type: {mimetype}\r\n\r\n".encode()
    )
    chunks.append(content)
    chunks.append(f"\r\n--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def cmd_upload(args, key):
    path = args.file
    filename = os.path.basename(path)
    with open(path, "rb") as fh:
        content = fh.read()
    mimetype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    prepared = api("POST", "/uploads/prepare", key, body={
        "filename": filename, "mimetype": mimetype, "size": len(content),
    })
    body, content_type = multipart(
        {"params": prepared["params"], "signature": prepared["signature"]}, "file", filename, content
    )
    req = urllib.request.Request(prepared["uploadUrl"], data=body, method="POST",
                                 headers={"content-type": content_type})
    with urllib.request.urlopen(req, timeout=300) as resp:
        resp.read()
    for _ in range(60):
        job = api("GET", f"/uploads/{prepared['id']}", key)
        if job.get("status") == "ready":
            return job
        if job.get("status") in ("failed", "expired"):
            print(json.dumps(job, indent=2), file=sys.stderr)
            sys.exit(1)
        time.sleep(2)
    print("upload did not become ready within 120s", file=sys.stderr)
    sys.exit(1)


def add_post_flags(parser):
    parser.add_argument("--title")
    parser.add_argument("--publish-at")
    parser.add_argument("--status")
    parser.add_argument("--notes")
    parser.add_argument("--profile")
    parser.add_argument("--copy")
    parser.add_argument("--copy-file")
    parser.add_argument("--asset", action="append")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("workspace")
    profiles = sub.add_parser("profiles")
    profiles.add_argument("--channel")
    posts = sub.add_parser("posts")
    posts.add_argument("--status")
    posts.add_argument("--channel")
    posts.add_argument("--limit", type=int, default=50)
    sub.add_parser("post").add_argument("id")
    create = sub.add_parser("create")
    add_post_flags(create)
    schedule = sub.add_parser("schedule")
    schedule.add_argument("id")
    schedule.add_argument("--publish-at")
    sub.add_parser("unschedule").add_argument("id")
    sub.add_parser("archive").add_argument("id")
    update = sub.add_parser("update")
    update.add_argument("id")
    add_post_flags(update)
    sub.add_parser("upload").add_argument("file")
    raw = sub.add_parser("raw")
    raw.add_argument("method")
    raw.add_argument("path")
    raw.add_argument("--body-file")
    args = parser.parse_args()
    key = load_api_key()

    if args.command == "workspace":
        out = api("GET", "/workspace", key)
    elif args.command == "profiles":
        out = api("GET", "/profiles/scheduling", key)
        if args.channel:
            out = [p for p in out if p.get("channel") == args.channel]
    elif args.command == "posts":
        out = cmd_posts(args, key)
    elif args.command == "post":
        out = api("GET", f"/posts/{args.id}", key)
    elif args.command == "create":
        missing = [f for f in ("title", "publish_at") if not getattr(args, f)]
        if missing or read_copy(args) is None:
            print("create needs --title, --publish-at, and --copy or --copy-file", file=sys.stderr)
            sys.exit(2)
        out = api("POST", "/posts", key, body=post_body(args, key, require_all=True))
    elif args.command == "schedule":
        body = {"publishAt": to_utc_iso(args.publish_at)} if args.publish_at else {}
        out = api("POST", f"/posts/{args.id}/schedule", key, body=body)
    elif args.command == "unschedule":
        out = api("POST", f"/posts/{args.id}/unschedule", key, body={})
    elif args.command == "archive":
        out = api("POST", f"/posts/{args.id}/archive", key, body={})
    elif args.command == "update":
        out = api("PATCH", f"/posts/{args.id}", key, body=post_body(args, key, require_all=False))
    elif args.command == "upload":
        out = cmd_upload(args, key)
    else:
        body = None
        if args.body_file:
            with open(args.body_file) as fh:
                body = json.load(fh)
        out = api(args.method.upper(), args.path, key, body=body)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
