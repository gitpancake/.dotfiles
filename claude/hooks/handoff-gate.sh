#!/usr/bin/env bash
# PreToolUse hook: block tool use at turn 50+ until a handoff doc exists for
# this session. Pairs with auto-handoff.sh (fires at 30).
#
# Normal path: auto-handoff writes the doc at turn 30 → sentinel present at 50
# → this hook no-ops. Fail-safe path: auto-handoff exited early (no transcript,
# no git, non-repo cwd) → no sentinel → this hook blocks until the user runs
# /handoff manually or restarts the session.
#
# Why: turn-cap-warn fires at 50 with 0% historical obedience. Auto-handoff at
# 30 captures cheap state automatically. The 50 gate makes ignoring the warning
# impossible — tools refuse until the doc exists on disk.
#
# Block via exit 2 → stderr surfaced back to Claude. Single tool lookups stay
# possible only after the block is satisfied.

set -u

input=$(cat)
sessionId=$(jq -r '.session_id // "unknown"' <<<"$input")
[[ "$sessionId" == "unknown" ]] && exit 0

logDir="${TMPDIR:-/tmp}/claude-turn-cap-warn"
counterFile="${logDir}/session-${sessionId}.count"
handoffMarker="${logDir}/session-${sessionId}.handoff"

current=$(cat "$counterFile" 2>/dev/null || echo 0)
(( current < 50 )) && exit 0

# Marker present + points at an existing file → pass.
if [[ -f "$handoffMarker" ]]; then
  outFile=$(cat "$handoffMarker" 2>/dev/null)
  if [[ -n "$outFile" && -f "$outFile" ]]; then
    exit 0
  fi
fi

cat >&2 <<EOF
🛑 HANDOFF GATE — turn ${current}, no auto-handoff doc found for this session.

auto-handoff.sh runs at turn 30 but appears to have exited early (no
transcript, no git, or write failure). Tools are blocked until a handoff
exists.

To unblock:
  1. Run /handoff to capture state manually, then /clear.
  2. The fresh session runs /resume to pick up.

Or restart the session if state loss is acceptable.
EOF
exit 2
