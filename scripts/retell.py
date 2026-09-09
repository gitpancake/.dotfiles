#!/usr/bin/env python3
"""Thin Retell API client — mirrors axiom.py / linear-gql.py.

Auth: resolves RETELL_API_KEY from env, then ~/.claude/.env, then ~/.pi/.env.
Bearer token in the Authorization header. Base: https://api.retellai.com
(both verified against node_modules/retell-sdk/src/client.ts and the
per-resource *.ts files in cartage-agent — paths below are not guessed).

Subcommands
  agents                    List agents [GET /list-agents].
  agent <id>                Get one agent [GET /get-agent/{id}].
  numbers                   List phone numbers [GET /list-phone-numbers].
  number <phone>            Get one phone number, incl. inbound_webhook_url
                             [GET /get-phone-number/{phone}] (E.164, e.g. +15555550123).
  llms                      List Retell LLMs [GET /list-retell-llms].
  llm <id>                  Get one Retell LLM [GET /get-retell-llm/{id}].
  calls [--limit N]         List calls [POST /v2/list-calls].
  call <id>                 Get one call [GET /v2/get-call/{id}].
  raw <path>                Escape hatch: GET by default; --method POST/PATCH/DELETE
                             with --body '<json>' for anything not wrapped above.

This is a debugging/setup skeleton (read-heavy, `raw` covers mutations) — it does not
replace RetellService.ts in the app itself. Extend by adding a subcommand near its
sibling rather than reaching for `raw` repeatedly for the same call.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

BASE_URL = os.environ.get("RETELL_API_BASE", "https://api.retellai.com")


def _from_env_files(name):
    for path in (os.path.expanduser("~/.claude/.env"), os.path.expanduser("~/.pi/.env")):
        try:
            with open(path) as fh:
                for line in fh:
                    line = line.strip()
                    if line.startswith(f"{name}="):
                        return line.split("=", 1)[1].strip().strip("'\"")
        except FileNotFoundError:
            continue
    return None


def load_auth():
    key = os.environ.get("RETELL_API_KEY") or _from_env_files("RETELL_API_KEY")
    if not key:
        print("RETELL_API_KEY not found (env, ~/.claude/.env, ~/.pi/.env)", file=sys.stderr)
        sys.exit(2)
    return key


def api(path, key, method="GET", body=None):
    url = path if path.startswith("http") else f"{BASE_URL}{path}"
    headers = {"authorization": f"Bearer {key}", "accept": "application/json"}
    data = None
    if body is not None:
        headers["content-type"] = "application/json"
        data = json.dumps(body).encode()
    req = urllib.request.Request(url, headers=headers, data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as err:
        detail = err.read()[:500].decode("utf-8", "replace")
        print(f"HTTP {err.code} on {method} {url}: {detail}", file=sys.stderr)
        raise


def main():
    parser = argparse.ArgumentParser(description="Retell API client")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("agents", help="list agents")

    p_agent = sub.add_parser("agent", help="get one agent")
    p_agent.add_argument("id")

    sub.add_parser("numbers", help="list phone numbers")

    p_number = sub.add_parser("number", help="get one phone number")
    p_number.add_argument("phone", help="E.164, e.g. +15555550123")

    sub.add_parser("llms", help="list Retell LLMs")

    p_llm = sub.add_parser("llm", help="get one Retell LLM")
    p_llm.add_argument("id")

    p_calls = sub.add_parser("calls", help="list calls")
    p_calls.add_argument("--limit", type=int, default=20)

    p_call = sub.add_parser("call", help="get one call")
    p_call.add_argument("id")

    p_raw = sub.add_parser("raw", help="GET a path, or --method POST/PATCH/DELETE with --body")
    p_raw.add_argument("path")
    p_raw.add_argument("--method", default="GET", choices=["GET", "POST", "PATCH", "DELETE"])
    p_raw.add_argument("--body", help="JSON body for POST/PATCH")

    args = parser.parse_args()
    key = load_auth()

    if args.cmd == "agents":
        print(json.dumps(api("/list-agents", key), indent=2, default=str))
        return

    if args.cmd == "agent":
        print(json.dumps(api(f"/get-agent/{args.id}", key), indent=2, default=str))
        return

    if args.cmd == "numbers":
        print(json.dumps(api("/list-phone-numbers", key), indent=2, default=str))
        return

    if args.cmd == "number":
        print(json.dumps(api(f"/get-phone-number/{args.phone}", key), indent=2, default=str))
        return

    if args.cmd == "llms":
        print(json.dumps(api("/list-retell-llms", key), indent=2, default=str))
        return

    if args.cmd == "llm":
        print(json.dumps(api(f"/get-retell-llm/{args.id}", key), indent=2, default=str))
        return

    if args.cmd == "calls":
        result = api("/v2/list-calls", key, method="POST", body={"limit": args.limit})
        print(json.dumps(result, indent=2, default=str))
        return

    if args.cmd == "call":
        print(json.dumps(api(f"/v2/get-call/{args.id}", key), indent=2, default=str))
        return

    if args.cmd == "raw":
        body = json.loads(args.body) if args.body else None
        print(json.dumps(api(args.path, key, method=args.method, body=body), indent=2, default=str))
        return


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError:
        sys.exit(1)
