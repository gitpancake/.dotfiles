#!/usr/bin/env bash
# UserPromptSubmit hook: warn once per session when conversation gets long.
# Each user prompt counts as one turn. Long sessions = quadratic cache_read
# growth, the dominant cost driver in long Opus sessions.
#
# Threshold (fires once per session):
#   - 50 prompts → suggest /clear + re-brief from plan/ticket
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

current=$(cat "$counterFile" 2>/dev/null || echo 0)
current=$((current + 1))
echo "$current" > "$counterFile"

if (( current >= 50 )) && [[ ! -f "$warnedFile" ]]; then
  touch "$warnedFile"
  msg=$'⚠️  CONTEXT ECONOMY: '"$current"$' user prompts in this session. Long sessions pay cache_read on the full transcript every turn — cost grows quadratically.\n   Consider /clear and re-brief from plan/ticket. Plans live in ~/.claude/plans/<TICKET>.md.'
  jq -nc --arg m "$msg" '{systemMessage: $m}'
fi

exit 0
