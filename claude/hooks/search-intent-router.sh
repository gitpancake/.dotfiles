#!/usr/bin/env bash
# UserPromptSubmit hook: when a prompt reads like a broad codebase lookup, nudge
# toward Explore/general-purpose subagents BEFORE the first Read/Grep fires.
#
# Why: subagent-nudge.sh fires reactively after 15+ IO calls accumulate in the
# parent transcript — by then the cache_read damage is done. Catching the intent
# at prompt-submit time lets the model dispatch a subagent on the first turn,
# whose transcript dies with it (parent pays only the summary).
#
# Fires once per session, never blocks. Skips:
#   - prompts already starting with a slash command (intent already routed)
#   - prompts inside wt lanes (briefs routinely contain search vocab as
#     acceptance criteria, same false-fire shape as debug-router learned).

set -u

input=$(cat)
sessionId=$(jq -r '.session_id // "unknown"' <<<"$input")
prompt=$(jq -r '.prompt // empty' <<<"$input")
cwd=$(jq -r '.cwd // empty' <<<"$input")
[[ "$sessionId" == "unknown" ]] && exit 0
[[ -z "$prompt" ]] && exit 0

[[ "$prompt" =~ ^[[:space:]]*/ ]] && exit 0

if [[ -n "$cwd" && "$cwd" == */.claude/worktrees/* ]]; then
  exit 0
fi

promptLower=$(printf '%s' "$prompt" | tr '[:upper:]' '[:lower:]')

# Broad-lookup intent. Tight enough to avoid firing on incidental "find".
searchRe='(where (is|are|does|do) .*(defined|declared|live|used|set|called))'
searchRe+='|(find all .*(usages|references|callers|callsites|imports))'
searchRe+='|(search (the|this) (codebase|repo|repository|project) for)'
searchRe+='|(which (file|files|module|service) .*(contain|define|export|import|reference))'
searchRe+='|(look (through|across) .*(codebase|repo|files))'
searchRe+='|(audit (the|all|every) .*(usage|call|reference|file))'
searchRe+='|(list (all|every) .*(usage|caller|reference|callsite|file))'
searchRe+='|(every (place|file|caller|usage) (that|where) )'
searchRe+='|(grep (the|this) (codebase|repo))'
[[ "$promptLower" =~ $searchRe ]] || exit 0

logDir="${HOME}/.claude/state/turn-counters"
mkdir -p "$logDir"
warnedFile="${logDir}/session-${sessionId}.warned"
touch "$warnedFile"
source "$(dirname "$0")/_warn-helpers.sh"
shouldFireOnce "search-intent-router" "$warnedFile" || exit 0

visible=$'🔭 Broad-lookup intent detected. Dispatch a subagent so the search transcript dies with it:\n  Agent(subagent_type=Explore)         — read-only locator (find files / grep symbols / where-defined)\n  Agent(subagent_type=general-purpose) — multi-step research across many files'
directive="The user's prompt reads like a broad codebase lookup (find/where-is/which-file/audit-all/list-usages). **Strongly prefer dispatching an Explore or general-purpose subagent over running Read/Grep/Glob/Bash here directly.** Heavy IO in the parent transcript causes linear cache_read growth on every subsequent turn — the subagent's transcript dies with it, so the parent pays only for the returned summary. Specify search breadth (quick/medium/very thorough) in the prompt. Only skip the subagent if the lookup is a single, exact, already-known path."

jq -nc --arg m "$visible" --arg c "$directive" '{
  systemMessage: $m,
  hookSpecificOutput: {
    hookEventName: "UserPromptSubmit",
    additionalContext: $c
  }
}'

exit 0
