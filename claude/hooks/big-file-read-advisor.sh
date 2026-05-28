#!/usr/bin/env bash
# PreToolUse hook: nudge when a Read call would slurp a >500-line file without
# offset/limit. The global CLAUDE.md §Cost Discipline rule says "never full-read
# a big file to find one symbol — grep first, then targeted read" — this hook
# is the enforcement layer for that rule, since it's purely compliance-dependent
# otherwise.
#
# Behavior:
#   - Matches tool_name == "Read"
#   - Skips if offset or limit already set (bounded read = fine)
#   - Skips if file doesn't exist (Read will error on its own)
#   - Skips images/PDFs/notebooks (line count meaningless)
#   - Counts lines once; if > 500, emits a systemMessage + additionalContext
#   - Fires at most once per (session, file) pair to avoid spam
#
# Never blocks — exits 0. The Read still happens. Goal is the next call, not
# this one.

set -u

input=$(cat)
sessionId=$(jq -r '.session_id // "unknown"' <<<"$input")
toolName=$(jq -r '.tool_name // empty' <<<"$input")
[[ "$toolName" != "Read" ]] && exit 0
[[ "$sessionId" == "unknown" ]] && exit 0

filePath=$(jq -r '.tool_input.file_path // empty' <<<"$input")
offset=$(jq -r '.tool_input.offset // empty' <<<"$input")
limit=$(jq -r '.tool_input.limit // empty' <<<"$input")

[[ -z "$filePath" ]] && exit 0
[[ -n "$offset" || -n "$limit" ]] && exit 0
[[ ! -f "$filePath" ]] && exit 0

case "${filePath##*.}" in
  png|jpg|jpeg|gif|webp|bmp|svg|pdf|ipynb) exit 0 ;;
esac

lines=$(wc -l < "$filePath" 2>/dev/null | tr -d ' ')
[[ -z "$lines" ]] && exit 0
(( lines > 500 )) || exit 0

logDir="${HOME}/.claude/state/turn-counters"
mkdir -p "$logDir"
warnedFile="${logDir}/session-${sessionId}.warned"
touch "$warnedFile"
source "$(dirname "$0")/_warn-helpers.sh"

# Sentinel keyed by file path hash so the warning fires once per (session, file).
fileTag="bigread:$(printf '%s' "$filePath" | shasum | cut -c1-12)"
shouldFireOnce "$fileTag" "$warnedFile" || exit 0

visible="📚 Reading ${filePath} (${lines} lines) without offset/limit. CLAUDE.md §Cost Discipline: grep first → targeted offset/limit Read. Full reads of >500-line files inflate every subsequent turn (cache_read on the whole content)."
directive="About to Read \`${filePath}\` (${lines} lines) without offset/limit. The global CLAUDE.md §Cost Discipline rule says: grep the file first to locate the section, then Read with bounded offset/limit. Full-reading big files is the single biggest source of linear cache_read growth in long sessions. If you're hunting one symbol, cancel this Read and run grep instead; if you genuinely need the whole file (small refactor, full review), proceed — but next time prefer the bounded pattern."

jq -nc --arg m "$visible" --arg c "$directive" '{
  systemMessage: $m,
  hookSpecificOutput: {
    hookEventName: "PreToolUse",
    additionalContext: $c
  }
}'

exit 0
