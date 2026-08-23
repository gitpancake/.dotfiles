#!/usr/bin/env bash
# Trigger, poll, or gate a Devin PR review without exposing credentials to the
# caller — and without the caller burning a model turn per poll.
# Usage:
#   devin-review.sh trigger <pr-url>            -> POST a review for the PR's current head sha
#   devin-review.sh status  <pr-url>            -> GET review status for the current head sha
#   devin-review.sh wait    <pr-url> [n] [sec]  -> poll status internally until terminal
#                                                  (default 10 attempts x 90s); prints final JSON
#   devin-review.sh gate    <pr-url> [n] [sec]  -> full review-gate round in ONE call:
#                                                  ensure a Devin review exists for the current
#                                                  head sha (trigger on 404/stale sha), wait for
#                                                  it, then wait for the arbiter commit status;
#                                                  prints a summary and exits:
#                                                    0 = arbiter success on head sha
#                                                    4 = timed out still pending/running
#                                                    5 = arbiter failure/error
#                                                    6 = needs-human-review (label or verdict)
# Lanes: use `gate` after every push instead of hand-rolled status/sleep loops —
# each hand-rolled poll is a full-context model turn spent reading "pending".
# Output: raw JSON (trigger/status/wait) or summary JSON (gate).
# 404 body = no review exists for the current head; 409 on trigger = already in flight.
set -euo pipefail

action="${1:-}"
pr_url="${2:-}"
if [[ -z "$action" || -z "$pr_url" ]]; then
  echo "usage: devin-review.sh trigger|status|wait|gate <pr-url> [attempts] [interval]" >&2
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

devin_trigger() {
  curl -s -X POST "$base" \
    -H "Authorization: Bearer $DEVIN_API_KEY" \
    -H 'Content-Type: application/json' \
    -d "{\"pr_url\":\"$pr_url\"}"
}

devin_status() {
  curl -s "$base?pr_url=$pr_url" -H "Authorization: Bearer $DEVIN_API_KEY"
}

json_field() { printf '%s' "$1" | jq -r "$2 // empty" 2>/dev/null || true; }

devin_wait() {
  local attempts=${1:-10} interval=${2:-90} i resp st
  for (( i = 1; i <= attempts; i++ )); do
    resp=$(devin_status)
    st=$(json_field "$resp" '.status')
    case "$st" in
      completed|errored|cancelled)
        printf '%s\n' "$resp"
        return 0 ;;
    esac
    (( i < attempts )) && sleep "$interval"
  done
  printf '%s\n' "$resp"
  echo "devin-review.sh: wait timed out after $attempts x ${interval}s (status: ${st:-none})" >&2
  return 4
}

# owner/repo/number out of https://github.com/{owner}/{repo}/pull/{n}
pr_parse() {
  owner=$(printf '%s' "$pr_url" | awk -F/ '{print $4}')
  repo=$(printf '%s' "$pr_url" | awk -F/ '{print $5}')
  number=$(printf '%s' "$pr_url" | awk -F/ '{print $7}')
  [[ -n "$owner" && -n "$repo" && -n "$number" ]] || {
    echo "devin-review.sh: cannot parse owner/repo/number from $pr_url" >&2
    exit 2
  }
}

arbiter_state() {
  gh api "repos/$owner/$repo/commits/$1/status" \
    --jq '[.statuses[] | select(.context == "arbiter")][0] | "\(.state)\t\(.description)"' \
    2>/dev/null || true
}

devin_gate() {
  local attempts=${1:-10} interval=${2:-90}
  pr_parse

  local head_sha labels
  head_sha=$(gh pr view "$pr_url" --json headRefOid --jq '.headRefOid')
  labels=$(gh pr view "$pr_url" --json labels --jq '[.labels[].name] | join(",")')

  local resp st sha
  resp=$(devin_status)
  st=$(json_field "$resp" '.status')
  sha=$(json_field "$resp" '.commit_sha')
  if [[ -z "$st" || ( -n "$sha" && "$sha" != "$head_sha" && "$st" != "running" && "$st" != "pending" ) ]]; then
    devin_trigger >/dev/null || true
  fi

  local i devin_st="" arb_line="" arb_state=""
  for (( i = 1; i <= attempts; i++ )); do
    resp=$(devin_status)
    devin_st=$(json_field "$resp" '.status')
    arb_line=$(arbiter_state "$head_sha")
    arb_state=${arb_line%%$'\t'*}
    labels=$(gh pr view "$pr_url" --json labels --jq '[.labels[].name] | join(",")')

    case ",$labels," in *,needs-human-review,*)
      emit_summary; echo "devin-review.sh: needs-human-review label — stop and report" >&2; return 6 ;;
    esac
    if [[ "$arb_state" == "success" || "$arb_state" == "failure" || "$arb_state" == "error" ]]; then
      case "$devin_st" in completed|errored|cancelled|"")
        emit_summary
        [[ "$arb_state" == "success" ]] && return 0 || return 5 ;;
      esac
    fi
    (( i < attempts )) && sleep "$interval"
  done

  emit_summary
  echo "devin-review.sh: gate timed out after $attempts x ${interval}s (devin: ${devin_st:-none}, arbiter: ${arb_state:-none})" >&2
  return 4
}

emit_summary() {
  jq -n \
    --arg head_sha "$head_sha" \
    --arg devin_status "${devin_st:-}" \
    --arg arbiter_state "${arb_state:-}" \
    --arg arbiter_description "${arb_line#*$'\t'}" \
    --arg labels "$labels" \
    '{head_sha: $head_sha, devin_status: $devin_status, arbiter_state: $arbiter_state,
      arbiter_description: $arbiter_description, labels: $labels}'
}

case "$action" in
  trigger) devin_trigger ;;
  status)  devin_status ;;
  wait)    devin_wait "${3:-10}" "${4:-90}" ;;
  gate)    devin_gate "${3:-10}" "${4:-90}" ;;
  *)
    echo "usage: devin-review.sh trigger|status|wait|gate <pr-url> [attempts] [interval]" >&2
    exit 2
    ;;
esac
