#!/usr/bin/env bash
# UserPromptSubmit hook: tiered warnings as conversation lengthens.
# Each user prompt counts as one turn. Long sessions = quadratic cache_read
# growth, the dominant cost driver in long Opus sessions.
#
# Thresholds (each fires once per session unless noted):
#   - 30 prompts → gentle reminder
#   - 50 prompts → strong suggestion to /clear + re-brief
#   - 75 prompts → PAUSE: ask Claude to stop and confirm before continuing
#   - 100+ prompts → hard nag every prompt thereafter
#
# Warnings surface to the user via systemMessage on stdout. Never blocks.

set -u

input=$(cat)
sessionId=$(jq -r '.session_id // "unknown"' <<<"$input")
[[ "$sessionId" == "unknown" ]] && exit 0

logDir="${TMPDIR:-/tmp}/claude-turn-cap-warn"
mkdir -p "$logDir"
counterFile="${logDir}/session-${sessionId}.count"
warnedFile="${logDir}/session-${sessionId}.warned"
touch "$warnedFile"
source "$(dirname "$0")/_warn-helpers.sh"

current=$(cat "$counterFile" 2>/dev/null || echo 0)
current=$((current + 1))
echo "$current" > "$counterFile"

msg=""

if (( current >= 100 )); then
  msg=$'🛑 SESSION OVERRUN: '"$current"$' prompts. Deep into quadratic-cost zone. /clear now. Re-brief from ~/.claude/plans/<TICKET>.md.'
elif (( current >= 75 )) && shouldFireOnce "tier75" "$warnedFile"; then
  msg=$'⏸️  TURN 75 — PAUSE. Claude: stop before next substantial work. Ask user to /clear and re-brief, or to explicitly confirm continuing. Plans live in ~/.claude/plans/<TICKET>.md.'
elif (( current >= 50 )) && shouldFireOnce "tier50" "$warnedFile"; then
  msg=$'⚠️  TURN 50 — STRONGLY SUGGEST /clear. Cost grows quadratically from here. Re-brief from plan/ticket. Past behavior: this warning gets ignored — escalate to user now, do not silently proceed.'
elif (( current >= 30 )) && shouldFireOnce "tier30" "$warnedFile"; then
  msg=$'💡 TURN 30. Consider a /clear soon. Cache_read on the transcript compounds each turn.'
fi

if [[ -n "$msg" ]]; then
  jq -nc --arg m "$msg" '{systemMessage: $m}'
fi

exit 0
