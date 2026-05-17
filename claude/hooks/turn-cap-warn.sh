#!/usr/bin/env bash
# UserPromptSubmit hook: tiered actions as conversation lengthens.
# Each user prompt counts as one turn. Long sessions = quadratic cache_read
# growth, the dominant cost driver in long Opus sessions.
#
# Thresholds:
#   - 20 prompts → gentle reminder (soft, once)
#   - 30 prompts → HARD HALT: inject mandatory directive forcing Claude to
#                  tell user to /clear, no other tool use this turn. The
#                  companion auto-handoff.sh has already written a handoff
#                  doc, so /clear is safe.
#   - 50/75/100 → re-fire halt directive (every turn past 30)
#
# Halts use hookSpecificOutput.additionalContext so the directive lands in
# Claude's context as a system instruction it must obey, plus a visible
# systemMessage for the user.

set -u

input=$(cat)
sessionId=$(jq -r '.session_id // "unknown"' <<<"$input")
cwd=$(jq -r '.cwd // empty' <<<"$input")
[[ "$sessionId" == "unknown" ]] && exit 0

logDir="${TMPDIR:-/tmp}/claude-turn-cap-warn"
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
# Ralph epic lane: also has scripts/ralph/ inside the worktree.
isLane=0
isRalph=0
if [[ -n "$cwd" && "$cwd" == */.claude/worktrees/* ]]; then
  isLane=1
  [[ -d "$cwd/scripts/ralph" ]] && isRalph=1
fi

if (( current >= 30 )); then
  # HARD HALT. Fires every turn past 30 — escalation, not once-only.
  handoffRef="${handoffPath:-~/.claude/handoffs/}"

  if (( isRalph == 1 )); then
    visible="🛑 TURN ${current} — HALT (Ralph lane). End this iteration. ralph.sh will start the next with fresh context."
    directive="MANDATORY HALT — turn ${current} reached inside a Ralph autonomous iteration. End this iteration NOW. Your ONLY allowed response is a short status line, then stop. Do NOT call any tool. The ralph.sh loop will pick up the next story with fresh context and the committed progress.txt + git state already capture what landed. The auto-handoff doc at ${handoffRef} is the backup. Reply pattern: 'Turn ${current} hard-halt. Iteration ended — ralph.sh next loop has fresh context. Progress committed.'"
  elif (( isLane == 1 )); then
    visible="🛑 TURN ${current} — HALT (autonomous lane). Stop and wait for the user to /resume in a fresh session."
    directive="MANDATORY HALT — turn ${current} reached inside an autonomous wt lane (cwd: ${cwd}). The lane ends here. Your ONLY allowed response is a short status line — commit any uncommitted work first if it is safe (one Bash call max to \`git status\` / \`git add -A && git commit\` is permitted, NOTHING else), then stop. Auto-handoff at ${handoffRef} captures live state. Reply pattern: 'Turn ${current} hard-halt — autonomous lane ending. Auto-handoff at <path>. User: /resume in a fresh wt or cockpit session to continue.'"
  else
    visible="🛑 TURN ${current} — HALT. Auto-handoff written. Run /clear now to start fresh."
    [[ -n "$handoffPath" ]] && visible+=$'\nHandoff: '"$handoffPath"
    directive="MANDATORY HALT — turn ${current} reached. Your ONLY allowed response this turn is a short message instructing the user to run /clear immediately. Do NOT call any tool (no Bash, no Read, no Edit, no Agent, no Skill). Do NOT continue the in-flight task. The auto-handoff doc at ${handoffRef} already captures state — a fresh session can /resume it. Refuse any temptation to 'just finish this one thing' — cache_read on this transcript is now quadratic and dominant cost. Reply pattern: 'Turn ${current} hard-halt. Auto-handoff at <path>. /clear now — fresh session can /resume.'"
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

if (( current >= 20 )) && shouldFireOnce "tier20" "$warnedFile"; then
  msg=$'💡 TURN 20. Hard halt at turn 30 — wrap the in-flight task before then.'
  jq -nc --arg m "$msg" '{systemMessage: $m}'
fi

exit 0
