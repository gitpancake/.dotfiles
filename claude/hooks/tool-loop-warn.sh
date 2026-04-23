#!/usr/bin/env bash
# PostToolUse hook: warn once per session when tool-call patterns suggest
# the "LLM-per-item" budget blowup.
#
# NOTE: PostToolUse hooks do NOT fire for subagent tool calls — only for the
# top-level session. Subagent tracking requires a Claude Code feature addition
# (filed: https://github.com/anthropics/claude-code/issues). The groupKey
# logic below is wired and ready for when CLAUDE_PARENT_SESSION_ID is added.
#
# Thresholds (each fires once per group):
#   - Same tool called >=30 times        -> suggests batch pattern
#   - Total tool calls in group >=100    -> suggests /clear between chunks
#
# Warnings surface to the user via systemMessage on stdout. Never blocks.

set -u

input=$(cat)
sessionId=$(jq -r '.session_id // "unknown"' <<<"$input")
toolName=$(jq -r '.tool_name // "unknown"' <<<"$input")

[[ "$sessionId" == "unknown" || "$toolName" == "unknown" ]] && exit 0

# Group subagents under their parent session when Claude sets the env var (B).
# Fall back (C): walk up the process tree to find the claude process PID.
#   - Parent session hook: spawned directly by Claude → found at depth 1
#   - Subagent hook: spawned by subagent shell → Claude found at depth 2
# Different tmux panes each have their own Claude process so stay isolated.
findClaudePid() {
  local pid=$$
  for _ in 1 2 3 4; do
    pid=$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ')
    [[ -z "$pid" || "$pid" == "1" ]] && break
    local comm
    comm=$(ps -o comm= -p "$pid" 2>/dev/null)
    [[ "$comm" == *claude* ]] && { echo "$pid"; return; }
  done
  echo ""
}

if [[ -n "${CLAUDE_PARENT_SESSION_ID:-}" ]]; then
  groupKey="$CLAUDE_PARENT_SESSION_ID"
else
  groupKey=$(findClaudePid)
  [[ -z "$groupKey" ]] && groupKey="$sessionId"
fi

logDir="${TMPDIR:-/tmp}/claude-tool-loop-warn"
mkdir -p "$logDir"
logFile="${logDir}/group-${groupKey}.log"
warnFile="${logDir}/group-${groupKey}.warned"
touch "$warnFile"

echo "$toolName" >> "$logFile"

totalCalls=$(awk 'END {print NR}' "$logFile")
sameToolCalls=$(grep -cx "$toolName" "$logFile")

warnings=()

shouldFireOnce() {
  local tag=$1
  grep -qx "$tag" "$warnFile" && return 1
  echo "$tag" >> "$warnFile"
  return 0
}

if (( sameToolCalls >= 30 )) && shouldFireOnce "sameTool:${toolName}"; then
  warnings+=(
    "⚠️  CONTEXT ECONOMY: ${toolName} called ${sameToolCalls}× across this session + subagents."
    "   Consider the batch pattern: one LLM call to produce a plan/map, then a"
    "   script to apply it — avoids per-item context re-reads at current prices."
  )
fi

if (( totalCalls >= 100 )) && shouldFireOnce "total100"; then
  warnings+=(
    "⚠️  CONTEXT ECONOMY: ${totalCalls} total tool calls across this session + subagents."
    "   Consider /clear between logical batches to reset the baseline."
  )
fi

if (( ${#warnings[@]} > 0 )); then
  combined=$(IFS=$'\n'; printf '%s' "${warnings[*]}")
  jq -nc --arg m "$combined" '{systemMessage: $m}'
fi

exit 0
