#!/usr/bin/env bash
# PostToolUse hook: warn once per session when tool-call patterns suggest
# the "LLM-per-item" budget blowup.
#
# Thresholds (each fires once per session):
#   - Same tool called >=30 times       -> suggests batch pattern
#   - Total tool calls in session >=100 -> suggests /clear between chunks
#
# Warnings surface to the user via systemMessage on stdout. Never blocks.

set -u

input=$(cat)
sessionId=$(jq -r '.session_id // "unknown"' <<<"$input")
toolName=$(jq -r '.tool_name // "unknown"' <<<"$input")

[[ "$sessionId" == "unknown" || "$toolName" == "unknown" ]] && exit 0

logDir="${TMPDIR:-/tmp}/claude-tool-loop-warn"
mkdir -p "$logDir"
logFile="${logDir}/${sessionId}.log"
warnFile="${logDir}/${sessionId}.warned"
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
    "⚠️  CONTEXT ECONOMY: ${toolName} has been called ${sameToolCalls}× this session."
    "   Consider the batch pattern: one LLM call to produce a plan/map, then a"
    "   script to apply it — avoids per-item context re-reads at current prices."
  )
fi

if (( totalCalls >= 100 )) && shouldFireOnce "total100"; then
  warnings+=(
    "⚠️  CONTEXT ECONOMY: ${totalCalls} tool calls this session."
    "   Context is re-read on every call. Consider /clear between logical"
    "   batches to reset the baseline and keep per-turn cost down."
  )
fi

if (( ${#warnings[@]} > 0 )); then
  combined=$(IFS=$'\n'; printf '%s' "${warnings[*]}")
  jq -nc --arg m "$combined" '{systemMessage: $m}'
fi

exit 0
