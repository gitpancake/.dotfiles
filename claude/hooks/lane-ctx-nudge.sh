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
# tier is evaluated):
#   130K — review-only remainder: finish it; full slice left: handoff
#   160K — handoff overdue
#   190K — quality degrades, stop now
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
(( ctx < 130000 )) && exit 0

ctxK=$((ctx / 1000))
if (( ctx >= 190000 )); then
  tier="tier190"
  visible="🔴 LANE CTX ${ctxK}K — quality degrades past this point. Commit + /handoff + lane-handoff.sh + stop."
  directive="Lane context is ${ctxK}K tokens — past 190K, output quality measurably degrades and every remaining message is bought at maximum cache-read cost. Commit whatever is safe RIGHT NOW (git add -A && git commit), run /handoff, then run ~/.claude/scripts/lane-handoff.sh <handoff-doc-path> as your FINAL tool call and stop — the lane runner respawns a fresh session that /resumes the doc and continues the brief, including any pending review loop. Without the lane-handoff.sh call nothing respawns and the lane dies mid-brief. Do not compact, do not start anything new."
elif (( ctx >= 160000 )); then
  tier="tier160"
  visible="🟠 LANE CTX ${ctxK}K — handoff overdue. Commit + /handoff + lane-handoff.sh + stop."
  directive="Lane context is ${ctxK}K tokens — the 120K handoff point is well past and cache reads now dominate cost. Finish only the single in-flight edit/test, commit, run /handoff, then run ~/.claude/scripts/lane-handoff.sh <handoff-doc-path> as your FINAL tool call and stop — the lane runner respawns a fresh session that /resumes the doc and continues the brief, including any pending review loop. Without the lane-handoff.sh call nothing respawns and the lane dies mid-brief. Do not compact."
else
  tier="tier130"
  visible="🟡 LANE CTX ${ctxK}K — review-only left? finish it. Full slice left? /handoff + lane-handoff.sh."
  directive="Lane context is ${ctxK}K tokens — past the ~120K handoff point. If implementation is shipped and only the review loop remains (poll for the bot comment, address findings, push), do NOT hand off — that is one poll loop plus one feedback pass; finish it and run lane-done.sh. Otherwise wrap the in-flight slice (commit it), run /handoff, then run ~/.claude/scripts/lane-handoff.sh <handoff-doc-path> as your FINAL tool call and stop — the lane runner respawns a fresh session that /resumes the doc and continues the brief, including any pending review loop. Do not compact."
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
