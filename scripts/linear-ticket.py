#!/usr/bin/env python3
"""linear-ticket — talk to Linear's GraphQL API directly, no MCP.

Replaces the Linear MCP server for the only things the workflow needs: create a
ticket (get the AE-NNNN) and post a comment. Keeping this out of MCP means lanes
never load the Linear tool schemas into context — the per-session tax that made
/ship (and every ao-coder session) expensive.

Subcommands:
  create   make an issue, print "<identifier>\\t<url>"  (used by /ship §2.5)
  comment  post a markdown comment on an existing issue by identifier

API key resolution (first hit wins):
  1. $LINEAR_API_KEY
  2. scripts/linear-ticket.config.local  (JSON: {"api_key": "lin_api_..."}, gitignored)
Mint a personal key at https://linear.app/settings/api (raw key, no Bearer prefix).

Exit nonzero on any hard failure so callers (ship.md §2.5, agents) can fall back
without blocking. Diagnostics go to stderr. API shape: OV resources/linear-api/.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API_URL = "https://api.linear.app/graphql"
CONFIG_LOCAL = Path(__file__).resolve().parent / "linear-ticket.config.local"

BOOTSTRAP_QUERY = """
query Bootstrap {
  viewer { id }
  teams {
    nodes {
      id
      name
      key
      states { nodes { id name type } }
      labels { nodes { id name } }
    }
  }
}
"""

CREATE_MUTATION = """
mutation Create($input: IssueCreateInput!) {
  issueCreate(input: $input) {
    success
    issue { id identifier url title }
  }
}
"""

ISSUE_BY_ID_QUERY = """
query IssueId($id: String!) {
  issue(id: $id) { id identifier }
}
"""

COMMENT_MUTATION = """
mutation Comment($input: CommentCreateInput!) {
  commentCreate(input: $input) {
    success
    comment { id url }
  }
}
"""


def die(msg: str):
    print(f"linear-ticket: {msg}", file=sys.stderr)
    sys.exit(1)


def resolve_api_key() -> str:
    key = os.environ.get("LINEAR_API_KEY", "").strip()
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
        "no API key — set $LINEAR_API_KEY or create "
        f"{CONFIG_LOCAL.name} with {{\"api_key\": \"lin_api_...\"}}"
    )


def graphql(api_key: str, query: str, variables: dict | None = None) -> dict:
    payload = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(
        API_URL,
        data=payload,
        headers={"Authorization": api_key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]
        die(f"HTTP {exc.code} from Linear: {detail}")
    except (urllib.error.URLError, TimeoutError) as exc:
        die(f"network error: {exc}")
    if body.get("errors"):
        msgs = "; ".join(e.get("message", str(e)) for e in body["errors"])
        die(f"GraphQL error: {msgs}")
    return body["data"]


def read_body(text: str | None, file_path: str | None) -> str:
    if text is not None:
        return text
    if file_path:
        return Path(file_path).read_text()
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return ""


def pick_team(teams: list[dict], wanted: str) -> dict:
    wanted_lc = wanted.lower()
    for team in teams:
        if team["name"].lower() == wanted_lc or team["key"].lower() == wanted_lc:
            return team
    names = ", ".join(f'{t["name"]} ({t["key"]})' for t in teams)
    die(f'team "{wanted}" not found. Available: {names}')


def pick_state_id(team: dict, wanted: str) -> str | None:
    states = team["states"]["nodes"]
    wanted_lc = wanted.lower()
    for state in states:
        if state["name"].lower() == wanted_lc:
            return state["id"]
    for state in states:
        if state["type"] == "started":
            return state["id"]
    print(
        f'linear-ticket: state "{wanted}" not found on team {team["key"]}; leaving default',
        file=sys.stderr,
    )
    return None


def pick_label_ids(team: dict, wanted: list[str]) -> list[str]:
    by_name = {lbl["name"].lower(): lbl["id"] for lbl in team["labels"]["nodes"]}
    ids = []
    for name in wanted:
        lid = by_name.get(name.lower())
        if lid:
            ids.append(lid)
        else:
            print(f'linear-ticket: label "{name}" not found; skipping', file=sys.stderr)
    return ids


def cmd_create(args: argparse.Namespace, api_key: str) -> None:
    data = graphql(api_key, BOOTSTRAP_QUERY)
    team = pick_team(data["teams"]["nodes"], args.team)

    issue_input: dict = {"teamId": team["id"], "title": args.title}
    description = read_body(args.description, args.description_file)
    if description.strip():
        issue_input["description"] = description
    if args.assignee == "me":
        issue_input["assigneeId"] = data["viewer"]["id"]
    if args.priority is not None:
        issue_input["priority"] = args.priority
    state_id = pick_state_id(team, args.state)
    if state_id:
        issue_input["stateId"] = state_id
    label_names = [s.strip() for s in args.labels.split(",") if s.strip()]
    if label_names:
        label_ids = pick_label_ids(team, label_names)
        if label_ids:
            issue_input["labelIds"] = label_ids

    result = graphql(api_key, CREATE_MUTATION, {"input": issue_input})
    payload = result["issueCreate"]
    if not payload.get("success"):
        die("issueCreate returned success=false")
    issue = payload["issue"]
    if args.json:
        print(json.dumps(issue))
    else:
        print(f'{issue["identifier"]}\t{issue["url"]}')


def cmd_comment(args: argparse.Namespace, api_key: str) -> None:
    body = read_body(args.body, args.body_file)
    if not body.strip():
        die("empty comment body (pass --body, --body-file, or pipe stdin)")
    found = graphql(api_key, ISSUE_BY_ID_QUERY, {"id": args.id})
    issue = found.get("issue")
    if not issue:
        die(f'issue "{args.id}" not found')
    result = graphql(
        api_key, COMMENT_MUTATION, {"input": {"issueId": issue["id"], "body": body}}
    )
    payload = result["commentCreate"]
    if not payload.get("success"):
        die("commentCreate returned success=false")
    if args.json:
        print(json.dumps(payload["comment"]))
    else:
        print(payload["comment"]["url"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Create Linear issues / post comments — no MCP.")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="create an issue, print id<tab>url")
    create.add_argument("--title", required=True)
    create.add_argument("--team", default="Autonomy Eng")
    create.add_argument("--state", default="In Progress")
    create.add_argument("--assignee", default="me", choices=["me", "none"])
    create.add_argument("--priority", type=int, choices=[0, 1, 2, 3, 4],
                        help="0 none, 1 urgent, 2 high, 3 medium, 4 low")
    create.add_argument("--labels", default="", help="comma-separated label names")
    create.add_argument("--description")
    create.add_argument("--description-file")
    create.add_argument("--json", action="store_true")

    comment = sub.add_parser("comment", help="post a comment on an issue by identifier")
    comment.add_argument("--id", required=True, help="issue identifier, e.g. AE-1234")
    comment.add_argument("--body")
    comment.add_argument("--body-file")
    comment.add_argument("--json", action="store_true")

    args = parser.parse_args()
    api_key = resolve_api_key()
    if args.command == "create":
        cmd_create(args, api_key)
    elif args.command == "comment":
        cmd_comment(args, api_key)


if __name__ == "__main__":
    main()
