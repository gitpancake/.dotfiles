#!/usr/bin/env bash
# Prunes ~/.claude/plans/<ID>.lint.md files for ticket IDs found in a git log range.
# Intended for use as a git post-merge hook on `main` — after a pull/merge,
# any lint plan whose ticket ID just landed in main is no longer needed.
#
# Usage:
#   prune-lint-on-merge.sh                # uses ORIG_HEAD..HEAD in current repo
#   prune-lint-on-merge.sh <range>        # explicit git log range
#
# Safe to run outside a hook; no-ops if not on main, no ORIG_HEAD, no matches.

set -euo pipefail

branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
[ "$branch" = "main" ] || exit 0

plans_dir="$HOME/.claude/plans"
[ -d "$plans_dir" ] || exit 0

range="${1:-ORIG_HEAD..HEAD}"
git rev-parse --verify -q "${range%%..*}" >/dev/null 2>&1 || exit 0
git rev-parse --verify -q "${range##*..}" >/dev/null 2>&1 || exit 0

ids=$(git log "$range" --oneline 2>/dev/null \
  | grep -oiE '(ae|aut|inf|eng|pro)-[0-9]+' \
  | tr '[:lower:]' '[:upper:]' \
  | sort -u)

[ -n "$ids" ] || exit 0

for id in $ids; do
  f="$plans_dir/$id.lint.md"
  if [ -f "$f" ]; then
    rm -v "$f"
  fi
done

exit 0
