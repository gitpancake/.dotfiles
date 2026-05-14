#!/usr/bin/env bash
# UserPromptSubmit hook: tiered warnings as conversation lengthens.
# Each user prompt counts as one turn. Long sessions = quadratic cache_read
# growth, the dominant cost driver in long Opus sessions.
#
# Thresholds (each fires once per session unless noted):
#   - 30 prompts → gentle reminder
#   - 50 prompts → strong suggestion to /handoff + /clear
#   - 75 prompts → PAUSE: ask Claude to stop and confirm before continuing
#   - 100+ prompts → hard nag every prompt thereafter
#
# Preferred response is /handoff (capture state to a doc the fresh session reads)
# then /clear — more context-efficient than riding the transcript into compaction.
# An autonomous lane should self-invoke /handoff on seeing the 50/75 warning.
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
  msg=$'🛑 SESSION OVERRUN: '"$current"$' prompts. Deep into quadratic-cost zone. /handoff now to capture state, then /clear — the fresh session reads the handoff doc.'
elif (( current >= 75 )) && shouldFireOnce "tier75" "$warnedFile"; then
  msg=$'⏸️  TURN 75 — PAUSE. Claude: stop before next substantial work. Run /handoff to capture state, then ask the user to /clear (or explicitly confirm continuing). Autonomous lane → self-invoke /handoff now.'
elif (( current >= 50 )) && shouldFireOnce "tier50" "$warnedFile"; then
  msg=$'⚠️  TURN 50 — STRONGLY SUGGEST /handoff then /clear. /handoff writes a doc the fresh session picks up — cheaper than compaction. Past behavior: this warning gets ignored — escalate to user now, do not silently proceed.'
elif (( current >= 30 )) && shouldFireOnce "tier30" "$warnedFile"; then
  msg=$'💡 TURN 30. Consider /handoff + /clear soon. Cache_read on the transcript compounds each turn.'
fi

if [[ -n "$msg" ]]; then
  jq -nc --arg m "$msg" '{systemMessage: $m}'
fi

exit 0
