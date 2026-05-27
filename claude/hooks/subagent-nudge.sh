#!/usr/bin/env bash
# PostToolUse hook: nudge once per session when the parent thread is doing
# heavy file-IO / shell work and has spawned ZERO sub-agents. That shape is
# the classic cache_read blow-up — every Read/Bash result sticks to the
# parent transcript and gets re-read on every subsequent turn.
#
# Rule: 30+ Read|Bash|Grep|Glob calls and 0 Task calls → soft warning, once.
#
# Use Explore (read-only research) or general-purpose (multi-step lookups)
# for searches whose findings won't be revisited in detail. The sub-agent's
# transcript dies with the sub-agent, so the parent only pays for its summary.
#
# Never blocks. systemMessage on stdout.

set -u

input=$(cat)
sessionId=$(jq -r '.session_id // "unknown"' <<<"$input")
toolName=$(jq -r '.tool_name // "unknown"' <<<"$input")
[[ "$sessionId" == "unknown" ]] && exit 0

logDir="${HOME}/.claude/state/turn-counters"
mkdir -p "$logDir"
ioFile="${logDir}/session-${sessionId}.iocount"
taskFile="${logDir}/session-${sessionId}.taskcount"
warnedFile="${logDir}/session-${sessionId}.warned"
touch "$warnedFile"
source "$(dirname "$0")/_warn-helpers.sh"

case "$toolName" in
  Read|Bash|Grep|Glob)
    io=$(cat "$ioFile" 2>/dev/null || echo 0); io=$((io + 1))
    echo "$io" > "$ioFile"
    ;;
  Task|Agent)
    t=$(cat "$taskFile" 2>/dev/null || echo 0); t=$((t + 1))
    echo "$t" > "$taskFile"
    ;;
  *)
    exit 0
    ;;
esac

io=$(cat "$ioFile" 2>/dev/null || echo 0)
tasks=$(cat "$taskFile" 2>/dev/null || echo 0)

if (( io >= 30 )) && (( tasks == 0 )) && shouldFireOnce "subagent-nudge" "$warnedFile"; then
  msg=$'🤝 '"${io}"$' Read/Bash/Grep calls, 0 sub-agents. Heavy IO accumulates in the parent transcript — every result re-reads on every later turn (linear cache_read growth). For broad searches/lookups, spawn Explore or general-purpose via Task. Their transcripts die with them; you only pay for the summary.'
  jq -nc --arg m "$msg" '{systemMessage: $m}'
fi

exit 0
