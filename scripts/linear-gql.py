#!/usr/bin/env python3
"""linear-gql — run ANY Linear GraphQL query/mutation, no MCP.

The general-purpose escape hatch that linear-ticket.py is not: linear-ticket.py
hardcodes create/comment/state, this passes an arbitrary operation straight to
Linear's GraphQL endpoint. Keeps Linear tool schemas out of every session's
context (the per-session tax MCP charged) while giving full API reach.

Query source (first hit wins): --query, --query-file, else stdin.
Variables:                       --variables '<json>' or --variables-file, default {}.

  # inline
  linear-gql.py --query 'query { viewer { id name } }'

  # from stdin (heredoc — no zsh echo/JSON escaping traps)
  linear-gql.py <<'GQL'
  query($id: String!) { issue(id: $id) { title state { name } } }
  GQL

  # with variables
  linear-gql.py --query-file q.graphql --variables '{"id":"AOA-42"}'

Prints the `data` object as pretty JSON on success. `--compact` for one line,
`--raw` to dump the whole envelope (incl. extensions). Exits nonzero on GraphQL
errors or transport failure; error messages go to stderr.

API key resolution (first hit wins):
  1. $LINEAR_API_KEY
  2. ~/.claude/.env / ~/.pi/.env  (KEY=value lines; sourced if present)
  3. scripts/linear-ticket.config.local  (JSON: {"api_key": "lin_api_..."})
Mint a personal key at https://linear.app/settings/api (raw key, no Bearer).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

API_URL = "https://api.linear.app/graphql"
CONFIG_LOCAL = Path(__file__).resolve().parent / "linear-ticket.config.local"
ENV_FILES = [Path.home() / ".claude" / ".env", Path.home() / ".pi" / ".env"]


def die(msg: str) -> None:
    print(f"linear-gql: {msg}", file=sys.stderr)
    sys.exit(1)


def _scan_env_files(name: str) -> str:
    pattern = re.compile(rf'^\s*(?:export\s+)?{re.escape(name)}\s*=\s*(.*)$')
    for path in ENV_FILES:
        if not path.exists():
            continue
        try:
            for line in path.read_text().splitlines():
                m = pattern.match(line)
                if m:
                    return m.group(1).strip().strip('"').strip("'")
        except OSError:
            continue
    return ""


def resolve_api_key() -> str:
    key = os.environ.get("LINEAR_API_KEY", "").strip()
    if key:
        return key
    key = _scan_env_files("LINEAR_API_KEY")
    if key:
        return key
    if CONFIG_LOCAL.exists():
        try:
            key = json.loads(CONFIG_LOCAL.read_text()).get("api_key", "").strip()
        except (json.JSONDecodeError, OSError) as exc:
            die(f"reading {CONFIG_LOCAL.name}: {exc}")
        if key:
            return key
    die(
        "no API key — set $LINEAR_API_KEY, add it to ~/.claude/.env, or create "
        f"{CONFIG_LOCAL.name} with {{\"api_key\": \"lin_api_...\"}}"
    )


def graphql(api_key: str, query: str, variables: dict) -> dict:
    payload = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        API_URL,
        data=payload,
        headers={"Authorization": api_key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:1000]
        die(f"HTTP {exc.code} from Linear: {detail}")
    except (urllib.error.URLError, TimeoutError) as exc:
        die(f"network error: {exc}")


def read_query(args: argparse.Namespace) -> str:
    if args.query is not None:
        return args.query
    if args.query_file:
        return Path(args.query_file).read_text()
    if not sys.stdin.isatty():
        data = sys.stdin.read()
        if data.strip():
            return data
    die("no query — pass --query, --query-file, or pipe one on stdin")


def read_variables(args: argparse.Namespace) -> dict:
    raw = None
    if args.variables is not None:
        raw = args.variables
    elif args.variables_file:
        raw = Path(args.variables_file).read_text()
    if raw is None or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        die(f"--variables is not valid JSON: {exc}")
    if not isinstance(parsed, dict):
        die("--variables must be a JSON object")
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run any Linear GraphQL query/mutation — no MCP.",
    )
    parser.add_argument("--query", help="inline GraphQL operation")
    parser.add_argument("--query-file", help="path to a .graphql file")
    parser.add_argument("--variables", help="variables as a JSON object string")
    parser.add_argument("--variables-file", help="path to a JSON variables file")
    parser.add_argument("--compact", action="store_true", help="one-line JSON output")
    parser.add_argument(
        "--raw",
        action="store_true",
        help="print the full response envelope (data + errors + extensions)",
    )
    args = parser.parse_args()

    query = read_query(args)
    variables = read_variables(args)
    api_key = resolve_api_key()
    body = graphql(api_key, query, variables)

    if args.raw:
        indent = None if args.compact else 2
        print(json.dumps(body, indent=indent))
        sys.exit(1 if body.get("errors") else 0)

    if body.get("errors"):
        msgs = "; ".join(e.get("message", str(e)) for e in body["errors"])
        die(f"GraphQL error: {msgs}")

    indent = None if args.compact else 2
    print(json.dumps(body.get("data"), indent=indent))


if __name__ == "__main__":
    main()
