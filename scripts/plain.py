#!/usr/bin/env python3
"""Thin passthrough for the Plain (support platform) GraphQL API.

Handles the auth header, the Cloudflare user-agent block, and cursor pagination
so callers only author GraphQL. See ~/.claude/skills/plain-api/SKILL.md.
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

ENDPOINT = "https://core-api.uk.plain.com/graphql/v1"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) plain-cli"


def loadKey():
    key = os.environ.get("PLAIN_API_KEY")
    if key:
        return key
    envPath = os.path.expanduser("~/.claude/.env")
    if os.path.exists(envPath):
        for line in open(envPath):
            m = re.match(r"^PLAIN_API_KEY=(.+)$", line.strip())
            if m:
                return m.group(1).strip().strip('"').strip("'")
    sys.exit("PLAIN_API_KEY not set and not found in ~/.claude/.env")


def run(query, variables):
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(
        ENDPOINT,
        data=body,
        headers={
            "Authorization": f"Bearer {loadKey()}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        resp = json.load(urllib.request.urlopen(req, timeout=30))
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:500]
        sys.exit(f"HTTP {e.code}: {detail}")
    if resp.get("errors"):
        print(json.dumps(resp["errors"], indent=2), file=sys.stderr)
        if not resp.get("data"):
            sys.exit(1)
    return resp.get("data")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--query", help="GraphQL document (or read from stdin)")
    p.add_argument("--query-file")
    p.add_argument("--variables", help="JSON object")
    p.add_argument("--variables-file")
    p.add_argument("--compact", action="store_true")
    args = p.parse_args()

    if args.query_file:
        query = open(args.query_file).read()
    elif args.query:
        query = args.query
    else:
        query = sys.stdin.read()

    variables = None
    if args.variables_file:
        variables = json.load(open(args.variables_file))
    elif args.variables:
        variables = json.loads(args.variables)

    data = run(query, variables)
    print(json.dumps(data) if args.compact else json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
