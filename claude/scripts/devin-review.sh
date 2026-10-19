#!/usr/bin/env bash
# Trigger, poll, or gate a PR review round without exposing credentials to the
# caller — and without the caller burning a model turn per poll.
# Usage:
#   devin-review.sh trigger  <pr-url>            -> POST a Devin review for the PR's current head sha
#   devin-review.sh status   <pr-url>            -> GET Devin review status for the current head sha
#   devin-review.sh wait     <pr-url> [n] [sec]  -> poll Devin status internally until terminal
#                                                   (default 10 attempts x 90s); prints final JSON
#   devin-review.sh findings <pr-url>            -> print every reviewer finding that applies to the
#                                                   current head sha (arbiter verdict, Devin/Greptile/
#                                                   Codex review bodies, inline comments) as markdown
#   devin-review.sh gate     <pr-url> [n] [sec]  -> full review-gate round in ONE call:
#                                                   ensure a Devin review exists for the head sha
#                                                   (trigger on 404/stale sha), wait for a SETTLED
#                                                   arbiter verdict, print summary JSON + findings,
#                                                   alert the cockpit (lane tab bell + macOS
#                                                   notification) on anything but success, and exit:
#                                                     0 = arbiter success on head sha
#                                                     4 = timed out still pending/running/unsettled
#                                                     5 = arbiter failure/error
#                                                     6 = arbiter needs-human verdict on head sha
#                                                         (the label is sticky and is never the signal)
#
# "Settled" — the reason gate exists: the arbiter posts a verdict on every push BEFORE any
# reviewer has read the sha, then re-runs after each reviewer round with a 180s settle.
# The first terminal status on a sha is therefore usually stale (PR #8665: push-time
# block at 03:01:00, Devin at 03:02:21, Greptile at 03:02:35, re-verdict at 03:06:44).
# gate only returns when the arbiter status on the head sha is newer than the newest
# reviewer output on that sha AND unchanged across two consecutive polls.
#
# Lanes: use `gate` after every push instead of hand-rolled status/sleep loops —
# each hand-rolled poll is a full-context model turn spent reading "pending", and the
# hand-rolled loop is what let stale verdicts through. Default window is 8 x 60s plus
# one 60s confirm poll (~9 min) so a gate always finishes inside the Bash tool's
# 10-minute ceiling — a gate killed at the ceiling prints nothing (PR #8667, exit 143).
# Progress goes to stderr every poll so a killed gate still leaves a trace.
# Output: raw JSON (trigger/status/wait), markdown (findings), summary JSON + findings
# markdown (gate). 404 body = no Devin review exists for the current head; 409 on
# trigger = already in flight.
set -euo pipefail

action="${1:-}"
pr_url="${2:-}"
if [[ -z "$action" || -z "$pr_url" ]]; then
  echo "usage: devin-review.sh trigger|status|wait|findings|gate <pr-url> [attempts] [interval]" >&2
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
reviewerLogins='"devin-ai-integration[bot]","chatgpt-codex-connector[bot]","greptile-apps[bot]"'
greptileCheckRun="Greptile Review"
findingBodyCap=6000

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
    st=$(json_field "$resp" '.status | strings')
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

# state \t created_at \t description of the newest arbiter status on a sha.
arbiter_state() {
  gh api "repos/$owner/$repo/commits/$1/status" \
    --jq '[.statuses[] | select(.context == "arbiter")][0] | select(. != null) | "\(.state)\t\(.created_at)\t\(.description)"' \
    2>/dev/null || true
}

# Newest reviewer output on a sha: review submissions, the Greptile check run,
# inline comments. Empty when no reviewer has touched the sha yet.
reviewer_latest() {
  local sha=$1
  {
    gh api "repos/$owner/$repo/pulls/$number/reviews" --paginate \
      --jq "[.[] | select(.commit_id == \"$sha\" and (.user.login | IN($reviewerLogins))) | .submitted_at] | max // empty" 2>/dev/null || true
    gh api "repos/$owner/$repo/commits/$sha/check-runs" \
      --jq "[.check_runs[] | select(.name == \"$greptileCheckRun\" and .status == \"completed\") | .completed_at] | max // empty" 2>/dev/null || true
    gh api "repos/$owner/$repo/pulls/$number/comments" --paginate \
      --jq "[.[] | select(.commit_id == \"$sha\" and (.user.login | IN($reviewerLogins))) | .created_at] | max // empty" 2>/dev/null || true
  } | grep . | sort | tail -n1 || true
}

print_findings() {
  local sha=$1
  printf '\n## Findings on %s\n' "${sha:0:8}"

  printf '\n### Arbiter verdict\n'
  gh api "repos/$owner/$repo/issues/$number/comments" --paginate \
    --jq "[.[] | select(.body | test(\"arbiter-sha: $sha\"))] | last | .body // empty" 2>/dev/null \
    | cut -c1-"$findingBodyCap" || true

  printf '\n### Review bodies\n'
  gh api "repos/$owner/$repo/pulls/$number/reviews" --paginate \
    --jq ".[] | select(.commit_id == \"$sha\" and (.user.login | IN($reviewerLogins)) and (.body | length) > 0) | \"#### \\(.user.login) (\\(.submitted_at))\\n\\(.body[0:$findingBodyCap])\\n\"" 2>/dev/null || true

  printf '\n### Inline comments still applying to this sha\n'
  gh api "repos/$owner/$repo/pulls/$number/comments" --paginate \
    --jq ".[] | select(.commit_id == \"$sha\" and (.user.login | IN($reviewerLogins)) and .in_reply_to_id == null) | \"- **\\(.user.login)** \`\\(.path):\\(.line // .original_line)\`\\n  \\(.body[0:$findingBodyCap] | gsub(\"\\n\"; \"\\n  \"))\\n\"" 2>/dev/null || true
}

lane_dir() {
  local dir="${CLAUDE_PROJECT_DIR:-$PWD}"
  [[ "$dir" == */.claude/worktrees/* ]] && printf '%s' "$dir"
}

# Alert the cockpit that a verdict landed. Two channels, both independent of the
# lane's agent-state paint (which repaints "busy" on the very next tool call):
#   - a BEL written to the lane pane's tty raises tmux's own bell flag, which
#     paints the tab in window-status-bell-style until the window is visited.
#     A BEL to stdout never gets there — the Bash tool captures it.
#   - a macOS notification carrying the PR number and verdict.
alert_lane() {
  local verdict=$1 dir label="" win="" tty=""
  dir=$(lane_dir) || true
  [[ -n "$dir" && -f "$dir/.claude/tmux-window" ]] && label=$(head -n1 "$dir/.claude/tmux-window")
  osascript -e "display notification \"PR #$number: $verdict\" with title \"Lane ${label:-$(basename "${dir:-$PWD}")}\" sound name \"Pop\"" >/dev/null 2>&1 || true
  if [[ -n "$label" ]]; then
    win=$(tmux list-windows -a -F '#{window_id} #{window_name}' 2>/dev/null \
      | awk -v l="$label" '$2 == l { print $1; exit }')
  fi
  if [[ -z "$win" && -n "${TMUX_PANE:-}" ]]; then
    win=$(tmux display-message -t "$TMUX_PANE" -p '#{window_id}' 2>/dev/null || true)
  fi
  [[ -z "$win" ]] && return 0
  tty=$(tmux list-panes -t "$win" -F '#{pane_tty}' 2>/dev/null | head -n1)
  [[ -n "$tty" && -w "$tty" ]] && printf '\a' > "$tty"
  return 0
}

devin_gate() {
  local attempts=${1:-8} interval=${2:-60}
  pr_parse

  local head_sha labels
  head_sha=$(gh pr view "$pr_url" --json headRefOid --jq '.headRefOid')
  labels=$(gh pr view "$pr_url" --json labels --jq '[.labels[].name] | join(",")')

  local resp st sha
  resp=$(devin_status)
  st=$(json_field "$resp" '.status | strings')
  sha=$(json_field "$resp" '.commit_sha')
  if [[ -z "$st" || ( -n "$sha" && "$sha" != "$head_sha" && "$st" != "running" && "$st" != "pending" ) ]]; then
    devin_trigger >/dev/null || true
  fi

  local i devin_st="" arb_line="" arb_state="" arb_at="" reviewer_at="" prev_arb_at="" settled="false"
  for (( i = 1; i <= attempts; i++ )); do
    resp=$(devin_status)
    devin_st=$(json_field "$resp" '.status | strings')
    sha=$(json_field "$resp" '.commit_sha')
    [[ -n "$sha" && "$sha" != "$head_sha" && "$devin_st" != "running" && "$devin_st" != "pending" ]] && devin_st=""
    arb_line=$(arbiter_state "$head_sha")
    arb_state=$(printf '%s' "$arb_line" | cut -f1)
    arb_at=$(printf '%s' "$arb_line" | cut -f2)
    reviewer_at=$(reviewer_latest "$head_sha")
    labels=$(gh pr view "$pr_url" --json labels --jq '[.labels[].name] | join(",")')

    local arb_terminal=false devin_terminal=false arb_fresh=false arb_stable=false
    case "$arb_state" in success|failure|error) arb_terminal=true ;; esac
    case "$devin_st" in completed|errored|cancelled|"") devin_terminal=true ;; esac
    [[ -n "$arb_at" && "$arb_at" > "$reviewer_at" ]] && arb_fresh=true
    [[ -n "$arb_at" && "$arb_at" == "$prev_arb_at" ]] && arb_stable=true
    printf 'gate %d/%d: arbiter=%s@%s reviewer=%s devin=%s fresh=%s stable=%s\n' \
      "$i" "$attempts" "${arb_state:-none}" "${arb_at:-none}" "${reviewer_at:-none}" "${devin_st:-none}" "$arb_fresh" "$arb_stable" >&2

    if $arb_terminal && $devin_terminal && $arb_fresh; then
      if $arb_stable; then
        settled="true"
        emit_summary
        print_findings "$head_sha" | tee_lane_findings
        [[ "$arb_state" == "success" ]] && return 0
        local arb_desc
        arb_desc=$(printf '%s' "$arb_line" | cut -f3- | cut -d'·' -f1)
        alert_lane "arbiter ${arb_state}: ${arb_desc}"
        case "$arb_desc" in needs-human*)
          echo "devin-review.sh: arbiter needs-human on $head_sha — address every finding above, push, gate once more, then report" >&2
          return 6 ;;
        esac
        echo "devin-review.sh: arbiter ${arb_state} on $head_sha — address every finding above, push, gate once more" >&2
        return 5
      fi
      prev_arb_at=$arb_at
      (( i < attempts )) && sleep "$(( interval < 60 ? interval : 60 ))"
      continue
    fi
    prev_arb_at=""
    (( i < attempts )) && sleep "$interval"
  done

  emit_summary
  print_findings "$head_sha" | tee_lane_findings
  alert_lane "gate unsettled after $attempts x ${interval}s (arbiter ${arb_state:-none}, reviewer output ${reviewer_at:-none})"
  echo "devin-review.sh: gate timed out after $attempts x ${interval}s (devin: ${devin_st:-none}, arbiter: ${arb_state:-none} at ${arb_at:-none}, newest reviewer output: ${reviewer_at:-none}) — call gate once more; still unsettled → lane-pause.sh review" >&2
  return 4
}

tee_lane_findings() {
  local dir
  dir=$(lane_dir) || true
  if [[ -n "$dir" ]]; then
    mkdir -p "$dir/.claude"
    tee "$dir/.claude/review-findings.md"
  else
    cat
  fi
}

emit_summary() {
  jq -n \
    --arg head_sha "$head_sha" \
    --arg devin_status "${devin_st:-}" \
    --arg arbiter_state "${arb_state:-}" \
    --arg arbiter_at "${arb_at:-}" \
    --arg arbiter_description "$(printf '%s' "${arb_line:-}" | cut -f3-)" \
    --arg reviewer_latest_at "${reviewer_at:-}" \
    --arg settled "${settled:-false}" \
    --arg labels "$labels" \
    '{head_sha: $head_sha, devin_status: $devin_status, arbiter_state: $arbiter_state,
      arbiter_at: $arbiter_at, arbiter_description: $arbiter_description,
      reviewer_latest_at: $reviewer_latest_at, settled: ($settled == "true"), labels: $labels}'
}

case "$action" in
  trigger)  devin_trigger ;;
  status)   devin_status ;;
  wait)     devin_wait "${3:-10}" "${4:-90}" ;;
  findings) pr_parse; print_findings "$(gh pr view "$pr_url" --json headRefOid --jq '.headRefOid')" ;;
  gate)     devin_gate "${3:-8}" "${4:-60}" ;;
  *)
    echo "usage: devin-review.sh trigger|status|wait|findings|gate <pr-url> [attempts] [interval]" >&2
    exit 2
    ;;
esac
