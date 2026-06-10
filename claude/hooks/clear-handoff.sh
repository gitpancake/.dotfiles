#!/usr/bin/env bash
# SessionEnd hook: when the user runs /clear, write a handoff doc *before* the
# context is wiped — unless the session is trivial or one was already captured
# (e.g. via /handoff).
#
# Why: /clear fires SessionEnd with session_end_reason="clear" while the
# transcript is still on disk. The audit showed /clear dominating at a p50 of
# ~2 turns — most state loss happens well below the turn cap. This is the
# automatic capture net.
#
# Not every /clear deserves a doc — a 2-turn throwaway has nothing to save.
# Floor: capture only if turns >= 5 OR context >= 100k tokens (the "few turns
# but heavy reads" case). Skip if a handoff already exists for this session.
#
# Output: ~/.claude/handoffs/<UTC>-auto-<branch>.md, picked up by /resume.

set -u

input=$(cat)
reason=$(jq -r '.session_end_reason // empty' <<<"$input")
[[ "$reason" != "clear" ]] && exit 0

sessionId=$(jq -r '.session_id // "unknown"' <<<"$input")
transcriptPath=$(jq -r '.transcript_path // empty' <<<"$input")
cwd=$(jq -r '.cwd // empty' <<<"$input")
[[ "$sessionId" == "unknown" ]] && exit 0
[[ -z "$transcriptPath" || ! -f "$transcriptPath" ]] && exit 0

source "$(dirname "$0")/_handoff-doc.sh"

logDir="${HOME}/.claude/state/turn-counters"
handoffMarker="${logDir}/session-${sessionId}.handoff"

# Already captured this session (a prior /clear attempt or /handoff) → done.
if [[ -f "$handoffMarker" ]]; then
  existing=$(cat "$handoffMarker" 2>/dev/null)
  [[ -n "$existing" && -f "$existing" ]] && exit 0
fi

# Turn count = real user prompts (string content) in the transcript. Derived
# here since turn-cap-warn.sh (the old counter writer) was retired 2026-06-09.
current=$(jq -rc 'select(.type=="user") | .message.content | if type=="string" then "u" else empty end' \
  "$transcriptPath" 2>/dev/null | wc -l | tr -d ' ')
current=${current:-0}
ctxTokens=$(effective_ctx_tokens "$transcriptPath")

# Trivial-session floor: nothing worth a doc.
if (( current < 5 )) && (( ctxTokens < 100000 )); then
  exit 0
fi

mkdir -p "$logDir"
outFile=$(write_handoff_doc "$sessionId" "$transcriptPath" "$cwd" "$current" "$ctxTokens" "clear")
echo "$outFile" > "$handoffMarker"

# SessionEnd output isn't surfaced interactively, but emit for log/debug parity.
msg=$'📝 Pre-clear handoff saved → '"${outFile}"$'\n\nFresh session run /resume to pick up.'
jq -nc --arg m "$msg" '{systemMessage: $m}'

exit 0
