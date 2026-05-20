#!/usr/bin/env bash
# UserPromptSubmit hook: when turn count >= 30 OR context tokens >= 300k
# (whichever hits first), mechanically generate a handoff doc from the
# transcript + git state without involving Claude.
#
# Why: turn-cap-warn fires at 30/50/75/100 but historical obedience is ~0%.
# /handoff invocations in the last 7d = 0; /clear = 315. Claude (and the user)
# /clear away long sessions and lose state. This hook decouples handoff
# creation from compliance — the doc exists before /clear is plausible.
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

logDir="${TMPDIR:-/tmp}/claude-turn-cap-warn"
counterFile="${logDir}/session-${sessionId}.count"
warnedFile="${logDir}/session-${sessionId}.warned"

current=$(cat "$counterFile" 2>/dev/null || echo 0)
# turn-cap-warn.sh runs after us and will increment the counter. Match its
# +1 semantic so we agree on the turn number being recorded this prompt.
current=$((current + 1))

# Effective context = last assistant message's input + cache_creation + cache_read.
# That's the prompt size billed on the next turn and what blows up cache_read cost.
ctxTokens=$(jq -rc 'select(.type=="assistant") | .message.usage // empty' "$transcriptPath" 2>/dev/null \
  | tail -1 \
  | jq -r '((.input_tokens // 0) + (.cache_creation_input_tokens // 0) + (.cache_read_input_tokens // 0))' 2>/dev/null)
ctxTokens=${ctxTokens:-0}

trigger=""
(( current >= 30 )) && trigger="turn"
(( ctxTokens >= 300000 )) && trigger="${trigger:+${trigger}+}ctx"
[[ -z "$trigger" ]] && exit 0

# Fire once per session.
[[ -f "$warnedFile" ]] && grep -qx "auto-handoff" "$warnedFile" && exit 0
mkdir -p "$logDir"
touch "$warnedFile"
echo "auto-handoff" >> "$warnedFile"

handoffDir="${HOME}/.claude/handoffs"
mkdir -p "$handoffDir"

ts=$(date -u +%Y-%m-%d-%H%M)
branch=""
gitStatus=""
gitDiffStat=""
if [[ -n "$cwd" && -d "$cwd/.git" || -n "$cwd" ]] && git -C "$cwd" rev-parse --git-dir &>/dev/null; then
  branch=$(git -C "$cwd" branch --show-current 2>/dev/null || echo "")
  gitStatus=$(git -C "$cwd" status --short 2>/dev/null | head -40)
  gitDiffStat=$(git -C "$cwd" diff --stat 2>/dev/null | tail -20)
fi
branchSlug=$(echo "${branch:-no-branch}" | tr '/' '-' | tr -cd 'a-zA-Z0-9-' | cut -c1-40)
outFile="${handoffDir}/${ts}-auto-${branchSlug}.md"

# Last 10 real user prompts (strip command wrappers + system-reminder noise).
lastPrompts=$(jq -r '
  select(.type=="user")
  | select(.message.content | type == "string")
  | .message.content
' "$transcriptPath" 2>/dev/null \
  | awk 'BEGIN{p=1} /^[[:space:]]*<system-reminder>/{p=0} /^[[:space:]]*<\/system-reminder>/{p=1; next} p' \
  | grep -Ev '^[[:space:]]*<(/?(command-(name|message|args|stdout)|local-command-[a-z-]+|system-reminder))>' \
  | grep -Ev '^[[:space:]]*Caveat:' \
  | sed '/./,$!d' \
  | tail -200)

# Last 20 tool calls (name + truncated input).
lastTools=$(jq -rc '
  select(.type=="assistant")
  | .message.content[]?
  | select(.type=="tool_use")
  | "\(.name): \((.input | tostring)[0:140])"
' "$transcriptPath" 2>/dev/null | tail -20)

# Active files: dedup file paths from Read/Edit/Write tool inputs.
activeFiles=$(jq -r '
  select(.type=="assistant")
  | .message.content[]?
  | select(.type=="tool_use")
  | select(.name=="Read" or .name=="Edit" or .name=="Write")
  | .input.file_path // empty
' "$transcriptPath" 2>/dev/null | awk '!seen[$0]++' | tail -15)

# Suggested skills — keyword heuristic over the last prompts.
skills=""
promptsLower=$(echo "$lastPrompts" | tr '[:upper:]' '[:lower:]')
echo "$promptsLower" | grep -qE '(failing test|tdd|red.green|test.first)' && skills+="- tdd"$'\n'
echo "$promptsLower" | grep -qE '(bug|broken|crash|fail|error|regress)' && skills+="- diagnose"$'\n'
echo "$promptsLower" | grep -qE '(scope|ticket|brief)' && skills+="- scope"$'\n'
echo "$promptsLower" | grep -qE '(ship|pr |pull request|create-pr)' && skills+="- ship"$'\n'
echo "$promptsLower" | grep -qE '(review|feedback|address)' && skills+="- address-feedback"$'\n'
[[ -z "$skills" ]] && skills="- (none inferred)"

{
  echo "# Auto-handoff — session ${sessionId:0:8} @ turn ${current} (ctx ${ctxTokens} tok)"
  echo ""
  echo "Generated mechanically by \`auto-handoff.sh\` (trigger: **${trigger}**) because turn count >= 30 or context >= 300k tokens — live state is at risk of being \`/clear\`ed away. Treat verbatim sections as the primary source — the structure is a dump, not a summary."
  echo ""
  echo "**CWD:** \`${cwd:-?}\`  "
  echo "**Branch:** \`${branch:-?}\`  "
  echo "**Turn:** ${current}  "
  echo "**Context tokens:** ${ctxTokens}  "
  echo "**UTC:** ${ts}"
  echo ""
  echo "## Suggested skills for next session"
  echo ""
  echo "$skills"
  echo "## Last user prompts (verbatim, oldest → newest)"
  echo ""
  echo '```'
  echo "$lastPrompts"
  echo '```'
  echo ""
  echo "## Recent tool calls (last 20)"
  echo ""
  echo '```'
  echo "$lastTools"
  echo '```'
  echo ""
  echo "## Active files touched"
  echo ""
  echo '```'
  echo "$activeFiles"
  echo '```'
  echo ""
  echo "## Git state"
  echo ""
  echo "**status:**"
  echo '```'
  echo "$gitStatus"
  echo '```'
  echo ""
  echo "**diff --stat:**"
  echo '```'
  echo "$gitDiffStat"
  echo '```'
} > "$outFile"

echo "$outFile" > "${logDir}/session-${sessionId}.handoff"

msg=$'📝 Auto-handoff saved → '"${outFile}"$'\n\n/clear is now safe — fresh session run /resume to pick up.'
jq -nc --arg m "$msg" '{systemMessage: $m}'

exit 0
