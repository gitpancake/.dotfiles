#!/usr/bin/env bash
# linear-brief.sh <LINEAR-ID> [area]
#
# Materialize a Linear ticket into a local brief file under $TICKETS_DIR so
# `wt` / `/pickup` can resolve and spawn a lane. Linear is the source of truth;
# $TICKETS_DIR is ONLY this cache (global CLAUDE.md §Ticket Lifecycle).
#
# The brief file is what the lane reads on disk on every resume — so "read the
# brief from Linear" means: fetch the ticket's description via the Linear API
# and write it as a proper brief (frontmatter `linear: <ID>`, which is exactly
# what `wt`'s find_ticket_by_linear greps for).
#
# Idempotent: if a brief with this linear id already exists, print its path and
# exit 0 — never clobber (lane `## Local notes` scratch survives). To pick up a
# fresh description after /rescope, delete the cache file and re-run.
#
# Prints the resolved brief path to stdout. Non-zero exit + stderr on failure.
set -euo pipefail

id_raw="${1:-}"
area="${2:-platform}"
[[ -n "$id_raw" ]] || { echo "usage: linear-brief.sh <LINEAR-ID> [area]" >&2; exit 2; }

id=$(printf '%s' "$id_raw" | tr '[:lower:]' '[:upper:]')
[[ "$id" =~ ^[A-Z]+-[0-9]+$ ]] || {
  echo "linear-brief: '$id_raw' is not a Linear id (expected TEAM-1234)" >&2; exit 2; }

TICKETS_DIR="${TICKETS_DIR:-$HOME/.claude/tickets}"
GQL="$HOME/.dotfiles/scripts/linear-gql.py"
[[ -x "$GQL" ]] || { echo "linear-brief: $GQL not found" >&2; exit 2; }

# 1. Idempotent — already materialized (or hand-scoped) locally? Use it as-is.
existing=$(grep -rlE "^linear:[[:space:]]+$id[[:space:]]*$" "$TICKETS_DIR" \
  --include='*.md' 2>/dev/null | head -1 || true)
[[ -n "$existing" ]] && { printf '%s\n' "$existing"; exit 0; }

# 2. Fetch the ticket from Linear. Capture to a tmp file — never echo JSON
#    through zsh (it mangles \n/\t in the description body).
tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
"$GQL" --variables "{\"id\":\"$id\"}" --compact > "$tmp" <<'GQL'
query($id: String!) {
  issue(id: $id) {
    identifier title description url
    state { name }
    project { name }
    parent { identifier }
  }
}
GQL

# 3. Parse + write the brief. Python handles the markdown body + slugify safely.
#    Base dir: $TICKETS_DIR if set (zsh chpwd points it at the project subtree),
#    else ~/.claude/tickets/<repo-basename>.
repo_base=""
if root=$(git rev-parse --show-toplevel 2>/dev/null); then
  repo_base=$(basename "$root")
fi

python3 - "$tmp" "$id" "$TICKETS_DIR" "$area" "$repo_base" <<'PY'
import json, sys, re, os, datetime

tmp, id_, tickets_dir, area, repo_base = sys.argv[1:6]

with open(tmp) as fh:
    data = json.load(fh)

issue = (data or {}).get("issue")
if not issue:
    sys.stderr.write(f"linear-brief: no Linear issue '{id_}'\n")
    sys.exit(3)

title = (issue.get("title") or "").strip()
desc = (issue.get("description") or "").strip()
url = issue.get("url") or ""
state = ((issue.get("state") or {}).get("name") or "").strip()
parent = ((issue.get("parent") or {}) or {}).get("identifier") or ""

# Slug from title: drop the Type: prefix, a trailing "(finish AO-1115)" aside,
# kebab-case, and strip bare numeric tokens (slug rule: no ids/numbers in slugs).
slug_src = re.sub(r'^(feature|fix|improvement|refactor|bug|spike)\s*:\s*', '', title, flags=re.I)
slug_src = re.sub(r'\s*\([^)]*\)\s*$', '', slug_src)
slug = re.sub(r'[^a-z0-9]+', '-', slug_src.lower())
slug = re.sub(r'(?<![a-z])\d+(?![a-z])', '', slug)   # kill standalone number tokens
slug = re.sub(r'-+', '-', slug).strip('-')[:50].strip('-')
if not slug:
    slug = id_.lower()

# Resolve base dir. If TICKETS_DIR is already project-scoped, use it; else nest
# under the repo basename so it lands in the right project subtree.
if tickets_dir:
    base = tickets_dir
    if repo_base and os.path.basename(base.rstrip('/')) != repo_base \
            and os.path.isdir(os.path.join(base, repo_base)):
        base = os.path.join(base, repo_base)
else:
    base = os.path.join(os.path.expanduser('~/.claude/tickets'), repo_base or '')

dest_dir = os.path.join(base, area)
os.makedirs(dest_dir, exist_ok=True)
dest = os.path.join(dest_dir, f"{slug}.md")

# Don't clobber a same-slug brief that belongs to a different ticket.
if os.path.exists(dest):
    with open(dest) as fh:
        head = fh.read(2000)
    m = re.search(r'^linear:\s*(\S+)', head, re.M)
    if not m or m.group(1).upper() != id_:
        dest = os.path.join(dest_dir, f"{slug}-{id_.lower()}.md")

created = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

fm = [
    "---",
    f"linear: {id_}",
    f"title: {title}",
    "status: open",
    f"epic: {parent}",
    f"area: {area}",
    "labels: []",
    f"created: {created}",
    "source: linear",
    "---",
    "",
    f"<!-- Materialized from Linear ({url}) by linear-brief.sh — this is the",
    "     ticket description verbatim, NOT a grilled /scope brief. Treat the",
    "     acceptance criteria as authoritative; infer surface area from the repo.",
    f"     Run `/rescope {id_}` to sharpen if the description is thin. -->",
    "",
    desc if desc else "_(Linear ticket has no description — /scope it.)_",
    "",
]

with open(dest, "w") as fh:
    fh.write("\n".join(fm))

print(dest)
PY
