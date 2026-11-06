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
# Tiers (each fires at most once per session; only the highest applicable
# tier is evaluated; scaled to the 400K window, 2026-07-14 — was
# 130K/160K/190K on the 200K window):
#   260K — review-only remainder: finish it; full slice left: handoff
#   320K — handoff overdue
#   380K — quality degrades, stop now; re-fires every 60K past it, because a
#          lane that ignores one reminder (review-only remainder, resumed
#          session) otherwise hears nothing again (one ran to 760K, 2026-10-15)
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

# Last assistant turn's billed context, read from the transcript tail only —
# full-file jq on a 100MB+ lane transcript per tool call is exactly the kind
# of waste this hook exists to prevent. sed 1d drops the line truncated by
# tail -c; a mid-write final line just falls out of the jq stream.
ctx=$(tail -c 524288 "$transcriptPath" | sed '1d' \
  | jq -rc 'select(.type=="assistant") | .message.usage // empty
      | ((.input_tokens // 0) + (.cache_creation_input_tokens // 0) + (.cache_read_input_tokens // 0))' 2>/dev/null \
  | tail -1)
[[ -z "$ctx" || ! "$ctx" =~ ^[0-9]+$ ]] && exit 0
(( ctx < 260000 )) && exit 0

# Post-PR tiers: 303 of 476 handoffs (7d to 2026-11-06) came after the PR was
# open, each a respawn that re-read ~98K of baseline to finish one gate round.
# The PR lookup is cached per session for 10 min; only reached past 260K.
prCacheFile="${logDir}/session-${sessionId}.pr-open"
if [[ ! -f "$prCacheFile" || -n "$(find "$prCacheFile" -mmin +10 2>/dev/null)" ]]; then
  prState=$(cd "$cwd" && gh pr view --json state -q .state 2>/dev/null || true)
  [[ "$prState" == "OPEN" ]] && echo 1 >"$prCacheFile" || echo 0 >"$prCacheFile"
fi
isPrOpen=false
[[ "$(cat "$prCacheFile" 2>/dev/null)" == "1" ]] && isPrOpen=true

ctxK=$((ctx / 1000))
if $isPrOpen; then
  (( ctx < 340000 )) && exit 0
  if (( ctx >= 375000 )); then
    tier="pr375-$((ctx / 15000))"
    visible="🔴 LANE CTX ${ctxK}K (PR open) — hand off now: short post-PR /handoff + lane-handoff.sh."
    directive="Lane context is ${ctxK}K tokens with the PR already open. Commit anything safe, run /handoff in its short post-PR form (PR URL, unpushed commits, open findings, what is left, gotchas — no re-verification checklist), then ~/.claude/scripts/lane-handoff.sh <handoff-doc-path> as your FINAL tool call and stop. Do not compact."
  else
    tier="pr340"
    visible="🟡 LANE CTX ${ctxK}K (PR open) — finish the review loop in this session; hand off only at 375K."
    directive="Lane context is ${ctxK}K tokens and the PR is open. Do NOT hand off: finish the remaining gate rounds, finding fixes, manual-test subagent dispatch and rebase in this session, then lane-done.sh or a pause code. Keep payloads small: findings and logs to a file then grep, screenshots only inside the manual-test subagent. The hook tells you at 375K if a handoff becomes necessary."
  fi
  shouldFireOnce "$tier" "$warnedFile" || exit 0
  jq -nc --arg m "$visible" --arg c "$directive" '{
    systemMessage: $m,
    hookSpecificOutput: { hookEventName: "PostToolUse", additionalContext: $c }
  }'
  exit 0
fi

if (( ctx >= 380000 )); then
  tier="tier380-$((ctx / 60000))"
  visible="🔴 LANE CTX ${ctxK}K — quality degrades past this point. Commit + /handoff + lane-handoff.sh + stop."
  directive="Lane context is ${ctxK}K tokens — past 380K, output quality measurably degrades and every remaining message is bought at maximum cache-read cost. Commit whatever is safe RIGHT NOW (git add -A && git commit), run /handoff, then run ~/.claude/scripts/lane-handoff.sh <handoff-doc-path> as your FINAL tool call and stop — the lane runner respawns a fresh session that /resumes the doc and continues the brief, including any pending review loop. Without the lane-handoff.sh call nothing respawns and the lane dies mid-brief. Do not compact, do not start anything new."
elif (( ctx >= 320000 )); then
  tier="tier320"
  visible="🟠 LANE CTX ${ctxK}K — handoff overdue. Commit + /handoff + lane-handoff.sh + stop."
  directive="Lane context is ${ctxK}K tokens — the 240K handoff point is well past and cache reads now dominate cost. Finish only the single in-flight edit/test, commit, run /handoff, then run ~/.claude/scripts/lane-handoff.sh <handoff-doc-path> as your FINAL tool call and stop — the lane runner respawns a fresh session that /resumes the doc and continues the brief, including any pending review loop. Without the lane-handoff.sh call nothing respawns and the lane dies mid-brief. Do not compact."
else
  tier="tier260"
  visible="🟡 LANE CTX ${ctxK}K — review-only left? finish it. Full slice left? /handoff + lane-handoff.sh."
  directive="Lane context is ${ctxK}K tokens — past the ~240K handoff point. If implementation is shipped and only the review loop remains (poll for the bot comment, address findings, push), do NOT hand off — that is one poll loop plus one feedback pass; finish it and run lane-done.sh. Otherwise wrap the in-flight slice (commit it), run /handoff, then run ~/.claude/scripts/lane-handoff.sh <handoff-doc-path> as your FINAL tool call and stop — the lane runner respawns a fresh session that /resumes the doc and continues the brief, including any pending review loop. Do not compact."
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
