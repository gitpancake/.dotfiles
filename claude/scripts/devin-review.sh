#!/usr/bin/env bash
# Trigger or poll a Devin PR review without exposing credentials to the caller.
# Usage:
#   devin-review.sh trigger <pr-url>   -> POST a review for the PR's current head sha
#   devin-review.sh status  <pr-url>   -> GET review status for the current head sha
# Output: the raw JSON response ({status, commit_sha, ...}); 404 body = no review
# exists for the current head (trigger one), 409 on trigger = already in flight.
set -euo pipefail

action="${1:-}"
pr_url="${2:-}"
if [[ -z "$action" || -z "$pr_url" ]]; then
  echo "usage: devin-review.sh trigger|status <pr-url>" >&2
  exit 2
fi

set -a
. "$HOME/.claude/.env.local"
set +a
if [[ -z "${DEVIN_API_KEY:-}" || -z "${DEVIN_ORG_ID:-}" ]]; then
  echo "devin-review.sh: DEVIN_API_KEY / DEVIN_ORG_ID missing from ~/.claude/.env.local" >&2
  exit 3
fi

base="https://api.devin.ai/v3/organizations/$DEVIN_ORG_ID/pr-reviews"
case "$action" in
  trigger)
    curl -s -X POST "$base" \
      -H "Authorization: Bearer $DEVIN_API_KEY" \
      -H 'Content-Type: application/json' \
      -d "{\"pr_url\":\"$pr_url\"}"
    ;;
  status)
    curl -s "$base?pr_url=$pr_url" -H "Authorization: Bearer $DEVIN_API_KEY"
    ;;
  *)
    echo "usage: devin-review.sh trigger|status <pr-url>" >&2
    exit 2
    ;;
esac
