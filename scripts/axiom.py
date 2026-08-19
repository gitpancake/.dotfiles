#!/usr/bin/env python3
"""Thin Axiom API client — mirrors granola.py / pocket.py / langsmith.py.

Auth: resolves AXIOM_TOKEN (or AXIOM_API_TOKEN) + AXIOM_ORG_ID from env, then
~/.claude/.env, then ~/.pi/.env. Bearer token + `x-axiom-org-id` header — BOTH
are required or the API 403s. Base: https://api.axiom.co.

Subcommands
  datasets                 List datasets (name + description) [GET /v1/datasets].
  query <apl>              Run an APL query [POST /v1/datasets/_apl?format=legacy].
                           Dataset goes INSIDE the APL: ["<dataset>"] | ...
                           Flattens matches -> {_time, ...data} and aggregation
                           buckets.totals -> {group..., op: value}. --start/--end
                           ISO passthrough (or just use ago(1h) in the APL itself).
                           --limit N caps printed rows; --json for the raw payload.
  schema <dataset>         Field names for a dataset (sampled from real events —
                           there is no /fields endpoint, and fieldsMetaMap is
                           always empty). Axiom serializes a match's top-level
                           columns under a `data` object in the response; those
                           keys ARE the APL columns, so they're reported unprefixed.
  monitors                 List monitors [GET /v2/monitors] (name/type/threshold/apl).
  raw <path>               GET an arbitrary path, or POST with --post --body '<json>'.

Response shape of _apl (legacy): {status, matches:[{_time,_sysTime,_rowId,data}],
buckets:{series, totals:[{group, aggregations:[{op,value}]}]}, fieldsMetaMap, ...}.
Raw queries land in `matches`; `summarize ... by <dim>` lands in `buckets.totals`.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = os.environ.get("AXIOM_API_BASE", "https://api.axiom.co")


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
    token = (
        os.environ.get("AXIOM_TOKEN")
        or os.environ.get("AXIOM_API_TOKEN")
        or _from_env_files("AXIOM_TOKEN")
        or _from_env_files("AXIOM_API_TOKEN")
    )
    org = os.environ.get("AXIOM_ORG_ID") or _from_env_files("AXIOM_ORG_ID")
    if not token:
        print("AXIOM_TOKEN not found (env, ~/.claude/.env, ~/.pi/.env)", file=sys.stderr)
        sys.exit(2)
    if not org:
        print("AXIOM_ORG_ID not found — Axiom API 403s without it", file=sys.stderr)
        sys.exit(2)
    return token, org


def api(path, token, org, method="GET", body=None):
    url = path if path.startswith("http") else f"{BASE_URL}{path}"
    headers = {"authorization": f"Bearer {token}", "x-axiom-org-id": org, "accept": "application/json"}
    data = None
    if body is not None:
        headers["content-type"] = "application/json"
        data = json.dumps(body).encode()
    req = urllib.request.Request(url, headers=headers, data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as err:
        detail = err.read()[:500].decode("utf-8", "replace")
        print(f"HTTP {err.code} on {method} {url}: {detail}", file=sys.stderr)
        raise


def run_apl(apl, token, org, start=None, end=None):
    body = {"apl": apl, "format": "legacy"}
    if start:
        body["startTime"] = start
    if end:
        body["endTime"] = end
    return api("/v1/datasets/_apl?format=legacy", token, org, method="POST", body=body)


def extract_rows(result):
    totals = ((result.get("buckets") or {}).get("totals")) or []
    if totals:
        rows = []
        for total in totals:
            row = dict(total.get("group") or {})
            for agg in total.get("aggregations") or []:
                row[agg.get("op") or "value"] = agg.get("value")
            rows.append(row)
        return rows
    rows = []
    for match in result.get("matches") or []:
        data = match.get("data")
        row = {"_time": match.get("_time")}
        if isinstance(data, dict):
            row.update(data)
        else:
            row["data"] = data
        rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser(description="Axiom API client")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("datasets", help="list datasets")

    p_q = sub.add_parser("query", help="run an APL query")
    p_q.add_argument("apl", help='APL, dataset inside: ["dataset"] | where ...')
    p_q.add_argument("--start", help="startTime ISO-8601 (optional; or use ago() in APL)")
    p_q.add_argument("--end", help="endTime ISO-8601 (optional)")
    p_q.add_argument("--limit", type=int, default=None, help="cap printed rows")
    p_q.add_argument("--json", action="store_true", help="print raw API payload")

    p_s = sub.add_parser("schema", help="field names for a dataset")
    p_s.add_argument("dataset")

    sub.add_parser("monitors", help="list monitors")

    p_raw = sub.add_parser("raw", help="GET a path, or POST with --post --body")
    p_raw.add_argument("path")
    p_raw.add_argument("--post", action="store_true")
    p_raw.add_argument("--body", help="JSON body for --post")

    args = parser.parse_args()
    token, org = load_auth()

    if args.cmd == "datasets":
        data = api("/v1/datasets", token, org)
        print(json.dumps([{"name": d.get("name"), "description": d.get("description")} for d in data], indent=2))
        return

    if args.cmd == "monitors":
        data = api("/v2/monitors", token, org)
        slim = [
            {
                "name": m.get("name"),
                "type": m.get("type"),
                "operator": m.get("operator"),
                "threshold": m.get("threshold"),
                "intervalMinutes": m.get("intervalMinutes"),
                "rangeMinutes": m.get("rangeMinutes"),
                "apl": m.get("aplQuery"),
                "id": m.get("id"),
            }
            for m in data
        ]
        print(json.dumps(slim, indent=2, default=str))
        return

    if args.cmd == "schema":
        result = run_apl(f'["{args.dataset}"] | limit 50', token, org)
        fields = set()
        for match in result.get("matches") or []:
            for key, value in match.items():
                if key == "data" and isinstance(value, dict):
                    fields.update(value.keys())
                else:
                    fields.add(key)
        ordered = sorted(fields)
        print(json.dumps({"dataset": args.dataset, "fieldCount": len(ordered), "fields": ordered}, indent=2))
        return

    if args.cmd == "raw":
        if args.post:
            body = json.loads(args.body) if args.body else {}
            print(json.dumps(api(args.path, token, org, method="POST", body=body), indent=2, default=str))
        else:
            print(json.dumps(api(args.path, token, org), indent=2, default=str))
        return

    if args.cmd == "query":
        result = run_apl(args.apl, token, org, args.start, args.end)
        if args.json:
            print(json.dumps(result, indent=2, default=str))
            return
        rows = extract_rows(result)
        if args.limit:
            rows = rows[: args.limit]
        status = result.get("status") or {}
        print(
            json.dumps(
                {
                    "rowsMatched": status.get("rowsMatched"),
                    "returned": len(rows),
                    "rows": rows,
                },
                indent=2,
                default=str,
            )
        )
        return


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError:
        sys.exit(1)
