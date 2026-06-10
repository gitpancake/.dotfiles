#!/usr/bin/env bash
# UserPromptSubmit hook: tiered actions as conversation lengthens.
# Each user prompt counts as one turn. Long sessions = quadratic cache_read
# growth, the dominant cost driver in long Opus sessions.
#
# Thresholds:
#   - 15 prompts → gentle reminder (soft, once)
#   - 20 prompts → HARD HALT: inject mandatory directive forcing Claude to
#                  tell user to /clear, no other tool use this turn.
#                  clear-handoff.sh captures state when /clear fires.
#   - past 20 → re-fire halt directive every turn (escalation, not once-only)
#
# Halts use hookSpecificOutput.additionalContext so the directive lands in
# Claude's context as a system instruction it must obey, plus a visible
# systemMessage for the user.

set -u

input=$(cat)
sessionId=$(jq -r '.session_id // "unknown"' <<<"$input")
cwd=$(jq -r '.cwd // empty' <<<"$input")
[[ "$sessionId" == "unknown" ]] && exit 0

logDir="${HOME}/.claude/state/turn-counters"
mkdir -p "$logDir"
counterFile="${logDir}/session-${sessionId}.count"
warnedFile="${logDir}/session-${sessionId}.warned"
touch "$warnedFile"
source "$(dirname "$0")/_warn-helpers.sh"

current=$(cat "$counterFile" 2>/dev/null || echo 0)
current=$((current + 1))
echo "$current" > "$counterFile"

handoffPath=""
[[ -f "${logDir}/session-${sessionId}.handoff" ]] && \
  handoffPath=$(cat "${logDir}/session-${sessionId}.handoff" 2>/dev/null || echo "")

# Detect autonomous wt lane: cwd lives under <repo>/.claude/worktrees/.
isLane=0
if [[ -n "$cwd" && "$cwd" == */.claude/worktrees/* ]]; then
  isLane=1
fi

if (( current >= 20 )); then
  # HARD HALT. Fires every turn past 20 — escalation, not once-only.
  if (( isLane == 1 )); then
    visible="🛑 TURN ${current} — HALT (autonomous lane). Stop and wait for the user to /resume in a fresh session."
    directive="MANDATORY HALT — turn ${current} reached inside an autonomous wt lane (cwd: ${cwd}). The lane ends here. Your ONLY allowed response is a short status line — commit any uncommitted work first if it is safe (one Bash call max to \`git status\` / \`git add -A && git commit\` is permitted, NOTHING else), then stop. Git history + the brief's Local notes are the carryover${handoffPath:+; handoff doc at ${handoffPath}}. Reply pattern: 'Turn ${current} hard-halt — autonomous lane ending. Progress committed. User: /resume in a fresh wt or cockpit session to continue.'"
  else
    visible="🛑 TURN ${current} — HALT. Run /clear now to start fresh (clear-handoff captures state on the way out)."
    [[ -n "$handoffPath" ]] && visible+=$'\nHandoff: '"$handoffPath"
    if [[ -n "$handoffPath" ]]; then
      stateNote="A handoff doc exists at ${handoffPath} — a fresh session can /resume it."
    else
      stateNote="clear-handoff.sh will capture state when /clear runs — a fresh session can /resume it."
    fi
    directive="MANDATORY HALT — turn ${current} reached. Your ONLY allowed response this turn is a short message instructing the user to run /clear immediately. Do NOT call any tool (no Bash, no Read, no Edit, no Agent, no Skill). Do NOT continue the in-flight task. ${stateNote} Refuse any temptation to 'just finish this one thing' — cache_read on this transcript is now quadratic and dominant cost. Reply pattern: 'Turn ${current} hard-halt. /clear now — fresh session can /resume.'"
  fi

  jq -nc --arg m "$visible" --arg c "$directive" '{
    systemMessage: $m,
    hookSpecificOutput: {
      hookEventName: "UserPromptSubmit",
      additionalContext: $c
    }
  }'
  exit 0
fi

if (( current >= 15 )) && shouldFireOnce "tier15" "$warnedFile"; then
  msg=$'💡 TURN 15. Hard halt at turn 20 — wrap the in-flight task before then.'
  jq -nc --arg m "$msg" '{systemMessage: $m}'
fi

exit 0
