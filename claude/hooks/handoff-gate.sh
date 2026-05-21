#!/usr/bin/env bash
# PreToolUse hook: HARD enforcement of the turn-20 halt. Pairs with
# turn-cap-warn.sh (advisory directive) + auto-handoff.sh (writes the doc).
#
# Why the rewrite: the old gate passed forever once the handoff doc existed
# ("marker present → exit 0"). Since auto-handoff writes that marker *at* turn
# 20, the gate self-disabled exactly when it was needed — turns 21+ all passed
# and interactive lanes ran unbounded, burning context + OAuth quota. The doc
# existing is the GREEN LIGHT TO RECYCLE, not a licence to keep working.
#
# New contract at turn >= 20:
#   - Block every tool (exit 2) — the lane/session must stop and recycle.
#   - ONE exception: a single work-saving git call (status / add / commit) so
#     in-flight work isn't lost. Consumed via a per-session sentinel; the
#     second save attempt is blocked too.
#   - push / gh / Edit / Read / Agent / everything else → blocked immediately.
#
# Recycle paths (out-of-process — hooks cannot run /clear or /resume):
#   - wt-loop / Ralph lane: claude exits, the outer loop spawns the next
#     iteration with fresh context that /resume's the auto-handoff doc.
#   - plain session: the user runs /clear then /resume.
#
# Block via exit 2 → stderr is surfaced back to Claude as the reason.

set -u

input=$(cat)
sessionId=$(jq -r '.session_id // "unknown"' <<<"$input")
[[ "$sessionId" == "unknown" ]] && exit 0

toolName=$(jq -r '.tool_name // empty' <<<"$input")
toolCmd=$(jq -r '.tool_input.command // empty' <<<"$input")

logDir="${TMPDIR:-/tmp}/claude-turn-cap-warn"
counterFile="${logDir}/session-${sessionId}.count"
handoffMarker="${logDir}/session-${sessionId}.handoff"
saveSentinel="${logDir}/session-${sessionId}.savedone"

current=$(cat "$counterFile" 2>/dev/null || echo 0)
(( current < 20 )) && exit 0

handoffPath=""
[[ -f "$handoffMarker" ]] && handoffPath=$(cat "$handoffMarker" 2>/dev/null)

# One-shot work-saving window: a single git status/add/commit is allowed so the
# halt never costs uncommitted work. Anything that publishes (push/gh) or keeps
# working (Edit/Read/Agent/...) is not a save — block it.
is_save_cmd() {
  local c=$1
  [[ "$c" == git*status* || "$c" == git*add* || "$c" == git*commit* ]] || return 1
  # Reject compound commands that smuggle a push / gh / network call.
  [[ "$c" == *push* || "$c" == *"gh "* || "$c" == *origin* ]] && return 1
  return 0
}

if [[ "$toolName" == "Bash" ]] && is_save_cmd "$toolCmd"; then
  if [[ ! -f "$saveSentinel" ]]; then
    mkdir -p "$logDir"
    touch "$saveSentinel"
    exit 0   # allow exactly one save, then the gate closes for good
  fi
fi

ref="${handoffPath:-~/.claude/handoffs/ (latest)}"
cat >&2 <<EOF
🛑 HANDOFF GATE — turn ${current}. Hard halt in effect; tools are blocked.

This session has passed the turn-20 cap. Continuing is quadratic cache_read
cost. State is already captured:
  handoff: ${ref}

Allowed: ONE git status/add/commit to save in-flight work (then blocked).
Blocked: everything else — push, gh, Edit, Read, Agent, Skill, further Bash.

Recycle to continue:
  - wt-loop / Ralph lane → end this iteration; the loop spawns the next with
    fresh context that /resume's the handoff above. Just stop.
  - plain session → /clear, then /resume in the fresh session.
EOF
exit 2
