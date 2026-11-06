#!/usr/bin/env bash
# PostToolUse hook: ambient context-size nudge for autonomous wt lanes.
#
# Why: the 14d audit (2026-06-09) showed lanes blowing past the 120K handoff
# doctrine — 107 sessions peaked >150K, <50% ever ran /handoff, ~$3K of
# cache-read spend bought past 150K. Turn-cap-warn couldn't see it: lanes run
# 300+ assistant messages per user turn, so UserPromptSubmit never fires
# mid-loop. PostToolUse does.
#
# Non-blocking by design: emits additionalContext (a reminder in the lane's
# own context) + a systemMessage. Never blocks a tool, never gates. Lane-only
# — cockpit sessions are untouched.
#
# Tiers come from ~/.claude/lane.config (defaults below if it is missing).
# Each fires at most once per session; only the highest applicable tier is
# evaluated. Before a PR: first = review-only remainder finishes, full slice
# hands off; second = handoff overdue; last = stop now, re-firing every
# LANE_CTX_REFIRE_PAST_LAST past it (one lane ran to 760K, 2026-10-15). With a
# PR open: first = finish in place; last = hand off, re-firing every
# LANE_CTX_POST_PR_REFIRE.
#
# Handoff = /handoff + lane-handoff.sh <doc> as the FINAL tool call: the
# state write is what wt-lanes' lane-run.sh keys on to respawn a fresh
# session that /resumes the doc. A /handoff without it strands the lane.

set -u

input=$(cat)

cwd=$(jq -r '.cwd // empty' <<<"$input")
[[ "$cwd" == */.claude/worktrees/* ]] || exit 0

sessionId=$(jq -r '.session_id // "unknown"' <<<"$input")
transcriptPath=$(jq -r '.transcript_path // empty' <<<"$input")
[[ "$sessionId" == "unknown" || -z "$transcriptPath" || ! -f "$transcriptPath" ]] && exit 0

logDir="${HOME}/.claude/state/turn-counters"
mkdir -p "$logDir"
warnedFile="${logDir}/session-${sessionId}.ctx-warned"
touch "$warnedFile"
source "$(dirname "$0")/_warn-helpers.sh"

LANE_CTX_PRE_PR_TIERS="260000 320000 380000"
LANE_CTX_POST_PR_TIERS="340000 375000"
LANE_CTX_REFIRE_PAST_LAST=60000
LANE_CTX_POST_PR_REFIRE=15000
[[ -f ~/.claude/lane.config ]] && source ~/.claude/lane.config
read -r preFirst preSecond preLast <<<"$LANE_CTX_PRE_PR_TIERS"
read -r postFirst postLast <<<"$LANE_CTX_POST_PR_TIERS"

# Last assistant turn's billed context, read from the transcript tail only —
# full-file jq on a 100MB+ lane transcript per tool call is exactly the kind
# of waste this hook exists to prevent. sed 1d drops the line truncated by
# tail -c; a mid-write final line just falls out of the jq stream.
ctx=$(tail -c 524288 "$transcriptPath" | sed '1d' \
  | jq -rc 'select(.type=="assistant") | .message.usage // empty
      | ((.input_tokens // 0) + (.cache_creation_input_tokens // 0) + (.cache_read_input_tokens // 0))' 2>/dev/null \
  | tail -1)
[[ -z "$ctx" || ! "$ctx" =~ ^[0-9]+$ ]] && exit 0
(( ctx < preFirst )) && exit 0

# Post-PR tiers: 303 of 476 handoffs (7d to 2026-11-06) came after the PR was
# open, each a respawn that re-read ~98K of baseline to finish one gate round.
# The PR lookup is cached per session for 10 min; only reached past the first pre-PR tier.
prCacheFile="${logDir}/session-${sessionId}.pr-open"
if [[ ! -f "$prCacheFile" || -n "$(find "$prCacheFile" -mmin +10 2>/dev/null)" ]]; then
  prState=$(cd "$cwd" && gh pr view --json state -q .state 2>/dev/null || true)
  [[ "$prState" == "OPEN" ]] && echo 1 >"$prCacheFile" || echo 0 >"$prCacheFile"
fi
isPrOpen=false
[[ "$(cat "$prCacheFile" 2>/dev/null)" == "1" ]] && isPrOpen=true

ctxK=$((ctx / 1000))
if $isPrOpen; then
  (( ctx < postFirst )) && exit 0
  if (( ctx >= postLast )); then
    tier="pr${postLast}-$((ctx / LANE_CTX_POST_PR_REFIRE))"
    visible="🔴 LANE CTX ${ctxK}K (PR open) — hand off now: short post-PR /handoff + lane-handoff.sh."
    directive="Lane context is ${ctxK}K tokens with the PR already open. Commit anything safe, run /handoff in its short post-PR form (PR URL, unpushed commits, open findings, what is left, gotchas — no re-verification checklist), then ~/.claude/scripts/lane-handoff.sh <handoff-doc-path> as your FINAL tool call and stop. Do not compact."
  else
    tier="pr${postFirst}"
    visible="🟡 LANE CTX ${ctxK}K (PR open) — finish the review loop in this session; hand off only at $((postLast / 1000))K."
    directive="Lane context is ${ctxK}K tokens and the PR is open. Do NOT hand off: finish the remaining gate rounds, finding fixes, manual-test subagent dispatch and rebase in this session, then lane-done.sh or a pause code. Keep payloads small: findings and logs to a file then grep, screenshots only inside the manual-test subagent. The hook tells you at $((postLast / 1000))K if a handoff becomes necessary."
  fi
  shouldFireOnce "$tier" "$warnedFile" || exit 0
  jq -nc --arg m "$visible" --arg c "$directive" '{
    systemMessage: $m,
    hookSpecificOutput: { hookEventName: "PostToolUse", additionalContext: $c }
  }'
  exit 0
fi

if (( ctx >= preLast )); then
  tier="tier${preLast}-$((ctx / LANE_CTX_REFIRE_PAST_LAST))"
  visible="🔴 LANE CTX ${ctxK}K — quality degrades past this point. Commit + /handoff + lane-handoff.sh + stop."
  directive="Lane context is ${ctxK}K tokens — past $((preLast / 1000))K, output quality measurably degrades and every remaining message is bought at maximum cache-read cost. Commit whatever is safe RIGHT NOW (git add -A && git commit), run /handoff, then run ~/.claude/scripts/lane-handoff.sh <handoff-doc-path> as your FINAL tool call and stop — the lane runner respawns a fresh session that /resumes the doc and continues the brief, including any pending review loop. Without the lane-handoff.sh call nothing respawns and the lane dies mid-brief. Do not compact, do not start anything new."
elif (( ctx >= preSecond )); then
  tier="tier${preSecond}"
  visible="🟠 LANE CTX ${ctxK}K — handoff overdue. Commit + /handoff + lane-handoff.sh + stop."
  directive="Lane context is ${ctxK}K tokens — well past the first nudge at $((preFirst / 1000))K and cache reads now dominate cost. Finish only the single in-flight edit/test, commit, run /handoff, then run ~/.claude/scripts/lane-handoff.sh <handoff-doc-path> as your FINAL tool call and stop — the lane runner respawns a fresh session that /resumes the doc and continues the brief, including any pending review loop. Without the lane-handoff.sh call nothing respawns and the lane dies mid-brief. Do not compact."
else
  tier="tier${preFirst}"
  visible="🟡 LANE CTX ${ctxK}K — review-only left? finish it. Full slice left? /handoff + lane-handoff.sh."
  directive="Lane context is ${ctxK}K tokens — past the first nudge at $((preFirst / 1000))K. If implementation is shipped and only the review loop remains (poll for the bot comment, address findings, push), do NOT hand off — that is one poll loop plus one feedback pass; finish it and run lane-done.sh. Otherwise wrap the in-flight slice (commit it), run /handoff, then run ~/.claude/scripts/lane-handoff.sh <handoff-doc-path> as your FINAL tool call and stop — the lane runner respawns a fresh session that /resumes the doc and continues the brief, including any pending review loop. Do not compact."
fi

shouldFireOnce "$tier" "$warnedFile" || exit 0

jq -nc --arg m "$visible" --arg c "$directive" '{
  systemMessage: $m,
  hookSpecificOutput: {
    hookEventName: "PostToolUse",
    additionalContext: $c
  }
}'
exit 0
