#!/usr/bin/env bash
# UserPromptSubmit + PostToolUse hook: when turn count >= 20 OR context tokens
# cross the session's threshold (300k normal, 120k inside an autonomous wt
# lane), mechanically generate a handoff doc from the transcript + git state
# without involving Claude.
#
# Dual-event binding rationale: autonomous lanes receive exactly ONE
# UserPromptSubmit (the kickoff) and then run as a long tool loop. The turn
# counter never advances past 1 and UserPromptSubmit never re-fires, so a
# UserPromptSubmit-only hook can't catch ctx blow-ups mid-loop. PostToolUse
# fires after every tool call, giving us a reliable ctx checkpoint inside
# autonomous runs. The sentinel makes it fire-once regardless of event.
#
# Lane-aware threshold: lanes degrade earlier than cockpit sessions — Ralph
# loop iterations + per-slice tool churn ramp context fast, and Claude
# "gets dumb" past ~120k well before the 300k mark that suits exploratory
# main sessions. Recycling cost is also lower in a lane (wt-loop spawns the
# next iteration that /resumes the handoff), so cut over sooner.
#
# Why: turn-cap-warn fires the hard halt at 20 with ~0% historical obedience.
# /clear-without-/handoff dominated the session log. This hook decouples
# handoff creation from compliance — the doc exists before /clear is plausible.
# clear-handoff.sh (SessionEnd reason=clear) is the companion that catches
# sessions that /clear *below* the turn cap.
#
# Output: ~/.claude/handoffs/<UTC>-auto-<branch>.md, picked up by /resume.
# systemMessage announces the path so the user knows /clear is safe. Once the
# doc exists, handoff-gate.sh blocks further tool use so the lane recycles.

set -u

input=$(cat)
sessionId=$(jq -r '.session_id // "unknown"' <<<"$input")
transcriptPath=$(jq -r '.transcript_path // empty' <<<"$input")
cwd=$(jq -r '.cwd // empty' <<<"$input")
eventName=$(jq -r '.hook_event_name // empty' <<<"$input")
[[ "$sessionId" == "unknown" ]] && exit 0
[[ -z "$transcriptPath" || ! -f "$transcriptPath" ]] && exit 0

source "$(dirname "$0")/_handoff-doc.sh"

logDir="${HOME}/.claude/state/turn-counters"
counterFile="${logDir}/session-${sessionId}.count"
warnedFile="${logDir}/session-${sessionId}.warned"

current=$(cat "$counterFile" 2>/dev/null || echo 0)
# On UserPromptSubmit, turn-cap-warn.sh runs after us and will increment the
# counter. Match its +1 semantic so we agree on the turn number being recorded
# this prompt. On PostToolUse the counter is already correct for the current
# turn — no increment.
if [[ "$eventName" != "PostToolUse" ]]; then
  current=$((current + 1))
fi

ctxTokens=$(effective_ctx_tokens "$transcriptPath")

# Lane detection matches turn-cap-warn.sh: cwd under <repo>/.claude/worktrees/.
ctxThreshold=300000
if [[ -n "$cwd" && "$cwd" == */.claude/worktrees/* ]]; then
  ctxThreshold=120000
fi

trigger=""
(( current >= 20 )) && trigger="turn"
(( ctxTokens >= ctxThreshold )) && trigger="${trigger:+${trigger}+}ctx"
[[ -z "$trigger" ]] && exit 0

# Fire once per session.
[[ -f "$warnedFile" ]] && grep -qx "auto-handoff" "$warnedFile" && exit 0
mkdir -p "$logDir"
touch "$warnedFile"
echo "auto-handoff" >> "$warnedFile"

outFile=$(write_handoff_doc "$sessionId" "$transcriptPath" "$cwd" "$current" "$ctxTokens" "$trigger")
echo "$outFile" > "${logDir}/session-${sessionId}.handoff"

# Lane auto-recycle: if cwd is a lane, fire tmux keys to /clear + /resume the
# lane pane after the gate has had time to block and settle. Lookup by
# pane_current_path (most reliable — tmux tracks per-pane cwd, while window/
# pane titles get clobbered by Claude's task-description updates).
laneRecycled=0
if [[ -n "$cwd" && "$cwd" == */.claude/worktrees/* ]] && command -v tmux >/dev/null 2>&1; then
  tmuxTarget=$(tmux list-panes -a -F '#{pane_id} #{pane_current_path}' 2>/dev/null \
    | awk -v C="$cwd" '$2==C {print $1; exit}')
  if [[ -n "$tmuxTarget" ]]; then
    # Fork detached so the hook completes without waiting. Sleep gives the
    # gate time to block + claude to print its halt message before keys land.
    nohup bash -c "
      sleep 12
      tmux send-keys -t '$tmuxTarget' '/clear' Enter
      sleep 2
      tmux send-keys -t '$tmuxTarget' '/resume $outFile' Enter
    " >/dev/null 2>&1 </dev/null &
    disown 2>/dev/null || true
    laneRecycled=1
  fi
fi

if (( laneRecycled )); then
  msg=$'📝 Auto-handoff saved → '"${outFile}"$'\n\nLane auto-recycle queued: /clear + /resume will fire in ~12s on tmux target '"${tmuxTarget}"'.'
else
  msg=$'📝 Auto-handoff saved → '"${outFile}"$'\n\n/clear is now safe — fresh session run /resume to pick up.'
fi
jq -nc --arg m "$msg" '{systemMessage: $m}'

exit 0
