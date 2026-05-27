#!/usr/bin/env bash
# UserPromptSubmit hook: when a prompt reads like a free-form debugging request,
# nudge toward the purpose-built tools instead of ad-hoc debugging.
#
# Why: the self-audit found 18 debug/investigate openers in 7 days ("why is PR
# #X failing", "tests failing", "broken") while /why-failing was invoked zero
# times and the diagnose skill barely. The tools exist; the habit doesn't. This
# closes the adoption gap by surfacing them at the moment of intent.
#
#   - /why-failing  → failing PR / CI: fetch checks, build a repro, root-cause.
#   - diagnose skill → local repro→minimise→fix→regression-test loop.
#
# Fires once per session and never blocks. additionalContext nudges Claude;
# systemMessage teaches the user the command exists. Skips prompts that already
# start with a slash command (intent already routed).

set -u

input=$(cat)
sessionId=$(jq -r '.session_id // "unknown"' <<<"$input")
prompt=$(jq -r '.prompt // empty' <<<"$input")
cwd=$(jq -r '.cwd // empty' <<<"$input")
[[ "$sessionId" == "unknown" ]] && exit 0
[[ -z "$prompt" ]] && exit 0

# Already a slash command → intent routed, stay quiet.
[[ "$prompt" =~ ^[[:space:]]*/ ]] && exit 0

# Skip autonomous wt lanes: their first prompt is the brief, and briefs
# routinely contain debug vocabulary ("failing test", "won't compile") as
# acceptance criteria — not debug intent. 7d data: 203 lane false fires vs
# 29 cockpit fires, desensitizing the model. Lanes already drive themselves
# off the brief; they don't need a debug nudge.
if [[ -n "$cwd" && "$cwd" == */.claude/worktrees/* ]]; then
  exit 0
fi

promptLower=$(printf '%s' "$prompt" | tr '[:upper:]' '[:lower:]')

# Debug-intent signal. Kept tight to avoid firing on incidental "error" mentions.
debugRe='(why (is|are|does|did|won.?t).*(fail|break|broke|error|crash))'
debugRe+='|(tests?.*(fail|break|red|skip))'
debugRe+='|((ci|build|pipeline|check).*(fail|red|broke))'
debugRe+='|(failing (test|ci|build|pr|check))'
debugRe+='|(not working|won.?t (build|compile|run|start))'
debugRe+='|(is broken|keeps (failing|crashing)|throwing|stack ?trace)'
[[ "$promptLower" =~ $debugRe ]] || exit 0

logDir="${HOME}/.claude/state/turn-counters"
mkdir -p "$logDir"
warnedFile="${logDir}/session-${sessionId}.warned"
touch "$warnedFile"
source "$(dirname "$0")/_warn-helpers.sh"
shouldFireOnce "debug-router" "$warnedFile" || exit 0

visible=$'🔎 Debug intent detected. Purpose-built tools:\n  /why-failing  — failing PR/CI: fetch checks → repro → root-cause\n  diagnose skill — local repro → minimise → fix → regression-test'
directive="The user's prompt reads like a debugging request. **Your next tool call MUST be the Skill tool** invoking either \`why-failing\` (failing PR / CI / remote check — fetches the run, reproduces, root-causes) or \`diagnose\` (local repro → minimise → hypothesise → fix → regression-test). Do NOT grep, Read, or Bash your way into this manually first — the skills already encode the loop and protect against coincidence-debugging (PP §44) and the missing sibling-grep at the end (PP §66). Only skip both if the request is clearly not a debugging task on closer read."

jq -nc --arg m "$visible" --arg c "$directive" '{
  systemMessage: $m,
  hookSpecificOutput: {
    hookEventName: "UserPromptSubmit",
    additionalContext: $c
  }
}'

exit 0
