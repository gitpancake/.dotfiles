#!/usr/bin/env bash
# PreToolUse hook: block tool use at turn 20+ until a handoff doc exists for
# this session. Pairs with auto-handoff.sh (fires at 20).
#
# Normal path: auto-handoff writes the doc at turn 20 → sentinel present → this
# hook no-ops. Fail-safe path: auto-handoff exited early (no transcript) → no
# sentinel → this hook blocks until the user runs /handoff manually or restarts
# the session.
#
# Why: turn-cap-warn fires the halt at 20 with 0% historical obedience.
# Auto-handoff at 20 captures cheap state automatically. The gate makes ignoring
# the halt impossible — tools refuse until the doc exists on disk.
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
(( current < 20 )) && exit 0

# Marker present + points at an existing file → pass.
if [[ -f "$handoffMarker" ]]; then
  outFile=$(cat "$handoffMarker" 2>/dev/null)
  if [[ -n "$outFile" && -f "$outFile" ]]; then
    exit 0
  fi
fi

cat >&2 <<EOF
🛑 HANDOFF GATE — turn ${current}, no auto-handoff doc found for this session.

auto-handoff.sh runs at turn 20 but appears to have exited early (no
transcript, or write failure). Tools are blocked until a handoff exists.

To unblock:
  1. Run /handoff to capture state manually, then /clear.
  2. The fresh session runs /resume to pick up.

Or restart the session if state loss is acceptable.
EOF
exit 2
