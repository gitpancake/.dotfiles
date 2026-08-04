#!/usr/bin/env python3
"""Thin LangSmith REST client — mirrors rootly.py / slack-bots.py.

No MCP (the LangSmith MCP is frequently unauthed in-session), no re-deriving the
API each time. Encodes the auth quirk, the runs/query gotchas, and the known
Cartage prod session so "look at run X" / "what tool-errored in prod today" is one call.

Auth: resolves LANGSMITH_API_KEY + LANGSMITH_WORKSPACE_ID from env, then
~/.claude/.env, then ~/.pi/.env. Never echoes them. The key is WORKSPACE-SCOPED:
every request sends BOTH  x-api-key: <key>  AND  X-Tenant-Id: <workspace id>,
else -> {"detail":"Forbidden"}.

Base: https://api.smith.langchain.com  (override LANGSMITH_ENDPOINT).

runs/query gotchas baked in:
  - session / start_time / run_type / trace / error are TOP-LEVEL params, NOT
    inside a `filter` expression (the filter-expr form silently returns empty).
  - limit max = 100 (higher -> "Limit exceeds maximum"). More than 100 -> follow
    cursors.next (pass it back as body["cursor"]). `runs --pages N` does this loop.
  - `--error` sends top-level error:true (server-side) — do NOT filter client-side
    on one page: errored runs are rare and usually past page 1, so a client-side
    scan silently returns nothing. error:true is honored and paginates normally.
  - errors live on llm/chain/tool child runs (e.g. AbortError on llm/chain), NOT
    on the root agent run — so `--error` deliberately does not force run_type=tool.

Known Cartage prod tracer session:
  agent-production  =  REDACTED-LANGSMITH-PROJECT-ID
  (plain `production` 438c68fe-... is empty)
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

# The two Cartage prod tracer sessions we actually fetch from.
AGENT_PROD = "REDACTED-LANGSMITH-PROJECT-ID"  # Wilson (cartage-agent)
EMPLOYEES_PROD = "REDACTED-LANGSMITH-PROJECT-ID"  # Chuck/Kelly/Jerry (ai-employees)

SESSION_ALIASES = {
    "prod": AGENT_PROD,
    "production": AGENT_PROD,
    "agent": AGENT_PROD,
    "agent-production": AGENT_PROD,
    "employees": EMPLOYEES_PROD,
    "employees-production": EMPLOYEES_PROD,
}
BOTH_PROD = ("agent-production", "employees-production")


def _endpoint():
    return (os.environ.get("LANGSMITH_ENDPOINT") or "https://api.smith.langchain.com").rstrip("/")


def _load(var):
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
    return None


def _headers():
    key = _load("LANGSMITH_API_KEY")
    tenant = _load("LANGSMITH_WORKSPACE_ID")
    if not key:
        sys.exit("LANGSMITH_API_KEY not found (env, ~/.claude/.env, ~/.pi/.env)")
    if not tenant:
        sys.exit("LANGSMITH_WORKSPACE_ID not found — the key is workspace-scoped, this header is required")
    return {"x-api-key": key, "X-Tenant-Id": tenant}


def call(method_path, params=None, body=None, post=False):
    url = f"{_endpoint()}/api/v1/{method_path.lstrip('/')}"
    headers = _headers()
    if post:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body or {}).encode()
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    else:
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as err:
        sys.exit(f"HTTP {err.code} on {method_path}: {err.read().decode()[:400]}")


def extract_run_id(ref):
    """Accept a bare run id or a LangSmith URL (…/runs/<id> or ?…runId=<id>)."""
    ref = ref.strip()
    m = re.search(r"/runs?/([0-9a-f-]{36})", ref) or re.search(r"[?&]runId=([0-9a-f-]{36})", ref)
    if m:
        return m.group(1)
    m = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", ref)
    return m.group(1) if m else ref


def _pp(obj):
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def resolve_session(ref):
    if re.fullmatch(r"[0-9a-f-]{36}", ref):
        return ref
    if ref in SESSION_ALIASES:
        return SESSION_ALIASES[ref]
    for s in call("sessions", {"limit": 100}):
        if s.get("name") == ref:
            return s["id"]
    sys.exit(f"session {ref!r} not found (try `langsmith sessions --match {ref}`)")


def cmd_sessions(a):
    rows = call("sessions", {"limit": 100})
    out = [
        {"id": s.get("id"), "name": s.get("name"), "run_count": s.get("run_count")}
        for s in rows
        if not a.match or a.match.lower() in (s.get("name", "") or "").lower()
    ]
    _pp(sorted(out, key=lambda r: (r.get("run_count") or 0), reverse=True))


def cmd_run(a):
    rid = extract_run_id(a.run)
    data = call(f"runs/{rid}")
    trace = data.get("trace_id") or rid
    if trace != rid and not a.no_follow:
        print(f"(child run — following to root {trace})", file=sys.stderr)
        data = call(f"runs/{trace}")
        rid = trace
    if a.json:
        _pp(data)
        return
    dur = ""
    try:
        from datetime import datetime

        s = datetime.fromisoformat(data["start_time"].replace("Z", "+00:00"))
        e = datetime.fromisoformat(data["end_time"].replace("Z", "+00:00"))
        dur = f"{(e - s).total_seconds():.1f}s"
    except Exception:
        pass
    print(f"Root: {data.get('name')} | status={data.get('status')} | duration={dur}")
    print(f"Tokens: {data.get('prompt_tokens', 0)} in / {data.get('completion_tokens', 0)} out")
    print(f"Session: {data.get('session_id')}  Trace: {data.get('trace_id')}")
    if data.get("error"):
        print(f"ERROR: {str(data['error'])[:400]}")
    print(f"Output: {(data.get('outputs_preview') or '')[:300]}")


def cmd_trace(a):
    rid = extract_run_id(a.run)
    root = call(f"runs/{rid}")
    trace_id = root.get("trace_id") or rid
    session_id = root.get("session_id")
    body = {
        "session": [session_id],
        "trace": trace_id,
        "select": ["name", "run_type", "status", "error", "dotted_order", "inputs_preview", "outputs_preview"],
        "limit": 100,
    }
    runs = call("runs/query", body=body, post=True).get("runs", [])
    runs = [r for r in runs if r.get("run_type") in ("tool", "llm")]
    runs.sort(key=lambda r: r.get("dotted_order", ""))
    if a.json:
        _pp(runs)
        return
    print(f"{len(runs)} meaningful runs (trace {trace_id}):\n")
    for i, r in enumerate(runs, 1):
        ok = "✓" if r.get("status") == "success" else "✗"
        print(f"{i:3}. {ok} [{r.get('run_type', ''):4}] {r.get('name', '')[:44]}")
        if r.get("inputs_preview"):
            print(f"      IN:  {r['inputs_preview'][:160]}")
        if r.get("outputs_preview"):
            print(f"      OUT: {r['outputs_preview'][:160]}")
        if r.get("error"):
            print(f"      ERR: {str(r['error'])[:200]}")


def cmd_runs(a):
    targets = list(BOTH_PROD) if a.session in ("both", "all") else [a.session]
    runs = []
    for name in targets:
        sid = resolve_session(name)
        cursor = None
        pages = 0
        while True:
            body = {"session": [sid], "limit": min(a.limit, 100)}
            if a.type:
                body["run_type"] = a.type
            if a.since:
                body["start_time"] = a.since
            if a.error:
                body["error"] = True  # server-side: errors live on llm/chain/tool runs
            body["select"] = ["name", "run_type", "status", "error", "start_time", "trace_id"]
            if cursor:
                body["cursor"] = cursor
            resp = call("runs/query", body=body, post=True)
            batch = resp.get("runs", [])
            for r in batch:
                r["_session"] = name
                runs.append(r)
            cursor = (resp.get("cursors") or {}).get("next")
            pages += 1
            if not cursor or not batch or pages >= a.pages:
                break
    if a.error:
        runs = [r for r in runs if r.get("error")]  # belt-and-suspenders
    if a.json:
        _pp(runs)
        return
    print(f"{len(runs)} run(s):\n", file=sys.stderr)
    for r in runs:
        ok = "✓" if r.get("status") == "success" else "✗"
        src = f"{{{r['_session'].split('-')[0]}}} " if len(targets) > 1 else ""
        print(f"{ok} {src}[{r.get('run_type', ''):4}] {r.get('name', '')[:44]}  trace={r.get('trace_id')}")
        if r.get("error"):
            print(f"    ERR: {str(r['error'])[:200]}")


def cmd_messages(a):
    rid = extract_run_id(a.run)
    data = call(f"runs/{rid}")
    messages = (data.get("inputs") or {}).get("messages") or []
    msgs = messages[0] if messages and isinstance(messages[0], list) else messages
    for i, msg in enumerate(msgs):
        if not isinstance(msg, dict):
            continue
        kwargs = msg.get("kwargs", {})
        mtype = msg.get("id", ["?"])[-1] if isinstance(msg.get("id"), list) else msg.get("type", "?")
        content = kwargs.get("content", "")
        if isinstance(content, list):
            content = " ".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in content)
        tool_calls = kwargs.get("tool_calls") or kwargs.get("additional_kwargs", {}).get("tool_calls") or []
        if content or tool_calls:
            print(f"[{i}] {mtype}: {str(content)[:400]}")
            if tool_calls:
                print(f"     CALLS: {json.dumps(tool_calls)[:300]}")


def cmd_raw(a):
    params, body = {}, None
    for kv in a.query or []:
        k, _, v = kv.partition("=")
        params[k] = v
    if a.body:
        body = json.loads(a.body)
    _pp(call(a.path, params=params or None, body=body, post=a.post))


def main():
    p = argparse.ArgumentParser(description="LangSmith REST client (Cartage)")
    sub = p.add_subparsers(dest="cmd", required=True)

    ps = sub.add_parser("sessions", help="list projects/sessions (by run_count desc)")
    ps.add_argument("--match")
    ps.set_defaults(fn=cmd_sessions)

    pr = sub.add_parser("run", help="summarize a run (auto-follows child -> root)")
    pr.add_argument("run", help="run id or LangSmith URL")
    pr.add_argument("--json", action="store_true")
    pr.add_argument("--no-follow", action="store_true")
    pr.set_defaults(fn=cmd_run)

    pt = sub.add_parser("trace", help="compact tool+llm timeline for a run's trace")
    pt.add_argument("run", help="run id or LangSmith URL")
    pt.add_argument("--json", action="store_true")
    pt.set_defaults(fn=cmd_trace)

    pm = sub.add_parser("messages", help="full message list of one llm run")
    pm.add_argument("run", help="run id or LangSmith URL")
    pm.set_defaults(fn=cmd_messages)

    pq = sub.add_parser("runs", help="query runs in a session (name/id, or 'prod')")
    pq.add_argument("session")
    pq.add_argument("--type", help="run_type: tool | llm | chain | ...")
    pq.add_argument("--since", help="ISO start_time lower bound, e.g. 2026-07-23T00:00:00Z")
    pq.add_argument("--error", action="store_true", help="only errored runs (server-side error:true)")
    pq.add_argument("--limit", type=int, default=100, help="per page, max 100")
    pq.add_argument("--pages", type=int, default=1, help="follow the cursor up to N pages (100/page)")
    pq.add_argument("--json", action="store_true")
    pq.set_defaults(fn=cmd_runs)

    pw = sub.add_parser("raw", help="call an arbitrary /api/v1 path")
    pw.add_argument("path")
    pw.add_argument("--query", action="append", help="k=v (repeatable, GET)")
    pw.add_argument("--body", help="JSON string (POST)")
    pw.add_argument("--post", action="store_true")
    pw.set_defaults(fn=cmd_raw)

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
