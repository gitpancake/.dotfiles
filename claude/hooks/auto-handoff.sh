#!/usr/bin/env bash
# UserPromptSubmit hook: when turn count >= 20 OR context tokens >= 300k
# (whichever hits first), mechanically generate a handoff doc from the
# transcript + git state without involving Claude.
#
# Why: turn-cap-warn fires the hard halt at 20 with ~0% historical obedience.
# /clear-without-/handoff dominated the session log. This hook decouples
# handoff creation from compliance — the doc exists before /clear is plausible.
# clear-handoff.sh (SessionEnd reason=clear) is the companion that catches
# sessions that /clear *below* the turn cap.
#
# Context threshold catches sessions that balloon token-wise without many
# turns (large file reads, big tool outputs) — same cache_read cost problem,
# different shape than turn-count-driven blow-ups.
#
# Output: ~/.claude/handoffs/<UTC>-auto-<branch>.md, picked up by /resume.
# systemMessage announces the path so the user knows /clear is safe.
#
# Runs AFTER turn-cap-warn.sh so the counter is current. Fires once per
# session (sentinel in the same warned-file used by turn-cap-warn).

set -u

input=$(cat)
sessionId=$(jq -r '.session_id // "unknown"' <<<"$input")
transcriptPath=$(jq -r '.transcript_path // empty' <<<"$input")
cwd=$(jq -r '.cwd // empty' <<<"$input")
[[ "$sessionId" == "unknown" ]] && exit 0
[[ -z "$transcriptPath" || ! -f "$transcriptPath" ]] && exit 0

source "$(dirname "$0")/_handoff-doc.sh"

logDir="${TMPDIR:-/tmp}/claude-turn-cap-warn"
counterFile="${logDir}/session-${sessionId}.count"
warnedFile="${logDir}/session-${sessionId}.warned"

current=$(cat "$counterFile" 2>/dev/null || echo 0)
# turn-cap-warn.sh runs after us and will increment the counter. Match its
# +1 semantic so we agree on the turn number being recorded this prompt.
current=$((current + 1))

ctxTokens=$(effective_ctx_tokens "$transcriptPath")

trigger=""
(( current >= 20 )) && trigger="turn"
(( ctxTokens >= 300000 )) && trigger="${trigger:+${trigger}+}ctx"
[[ -z "$trigger" ]] && exit 0

# Fire once per session.
[[ -f "$warnedFile" ]] && grep -qx "auto-handoff" "$warnedFile" && exit 0
mkdir -p "$logDir"
touch "$warnedFile"
echo "auto-handoff" >> "$warnedFile"

outFile=$(write_handoff_doc "$sessionId" "$transcriptPath" "$cwd" "$current" "$ctxTokens" "$trigger")
echo "$outFile" > "${logDir}/session-${sessionId}.handoff"

msg=$'📝 Auto-handoff saved → '"${outFile}"$'\n\n/clear is now safe — fresh session run /resume to pick up.'
jq -nc --arg m "$msg" '{systemMessage: $m}'

exit 0
