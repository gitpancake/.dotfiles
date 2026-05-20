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
[[ "$sessionId" == "unknown" ]] && exit 0
[[ -z "$prompt" ]] && exit 0

# Already a slash command → intent routed, stay quiet.
[[ "$prompt" =~ ^[[:space:]]*/ ]] && exit 0

promptLower=$(printf '%s' "$prompt" | tr '[:upper:]' '[:lower:]')

# Debug-intent signal. Kept tight to avoid firing on incidental "error" mentions.
debugRe='(why (is|are|does|did|won.?t).*(fail|break|broke|error|crash))'
debugRe+='|(tests?.*(fail|break|red|skip))'
debugRe+='|((ci|build|pipeline|check).*(fail|red|broke))'
debugRe+='|(failing (test|ci|build|pr|check))'
debugRe+='|(not working|won.?t (build|compile|run|start))'
debugRe+='|(is broken|keeps (failing|crashing)|throwing|stack ?trace)'
[[ "$promptLower" =~ $debugRe ]] || exit 0

logDir="${TMPDIR:-/tmp}/claude-turn-cap-warn"
mkdir -p "$logDir"
warnedFile="${logDir}/session-${sessionId}.warned"
touch "$warnedFile"
source "$(dirname "$0")/_warn-helpers.sh"
shouldFireOnce "debug-router" "$warnedFile" || exit 0

visible=$'🔎 Debug intent detected. Purpose-built tools:\n  /why-failing  — failing PR/CI: fetch checks → repro → root-cause\n  diagnose skill — local repro → minimise → fix → regression-test'
directive="The user's prompt reads like a debugging request. Prefer the purpose-built paths over ad-hoc debugging: if it concerns a failing PR or CI run, use the /why-failing command; for a local reproduce→minimise→fix→regression-test loop, use the diagnose skill. Only fall back to manual debugging if neither fits."

jq -nc --arg m "$visible" --arg c "$directive" '{
  systemMessage: $m,
  hookSpecificOutput: {
    hookEventName: "UserPromptSubmit",
    additionalContext: $c
  }
}'

exit 0
