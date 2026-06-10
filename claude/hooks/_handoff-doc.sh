#!/usr/bin/env bash
# Shared handoff-doc generator. Sourced by clear-handoff.sh (/clear trigger)
# and clear-handoff.sh (SessionEnd reason=clear trigger). Keeps the doc format
# in one place so both triggers emit identical, /resume-readable handoffs.
#
# No side effects on source — only defines functions.

# effective_ctx_tokens <transcriptPath>
# Echo the last assistant turn's billed context size (input + cache_create +
# cache_read). That's the prompt size billed next turn and what blows up
# cache_read cost. Echoes 0 if unparseable.
effective_ctx_tokens() {
  local transcriptPath=$1 ctx
  ctx=$(jq -rc 'select(.type=="assistant") | .message.usage // empty' "$transcriptPath" 2>/dev/null \
    | tail -1 \
    | jq -r '((.input_tokens // 0) + (.cache_creation_input_tokens // 0) + (.cache_read_input_tokens // 0))' 2>/dev/null)
  echo "${ctx:-0}"
}

# write_handoff_doc <sessionId> <transcriptPath> <cwd> <turn> <ctxTokens> <trigger>
# Writes ~/.claude/handoffs/<UTC>-auto-<branch>.md from the transcript + git
# state. Echoes the output path on stdout. Caller owns the once-per-session
# sentinel and the systemMessage.
write_handoff_doc() {
  local sessionId=$1 transcriptPath=$2 cwd=$3 current=$4 ctxTokens=$5 trigger=$6

  local handoffDir="${HOME}/.claude/handoffs"
  mkdir -p "$handoffDir"

  local ts branch="" gitStatus="" gitDiffStat=""
  ts=$(date -u +%Y-%m-%d-%H%M)
  if [[ -n "$cwd" ]] && git -C "$cwd" rev-parse --git-dir &>/dev/null; then
    branch=$(git -C "$cwd" branch --show-current 2>/dev/null || echo "")
    gitStatus=$(git -C "$cwd" status --short 2>/dev/null | head -40)
    gitDiffStat=$(git -C "$cwd" diff --stat 2>/dev/null | tail -20)
  fi
  local branchSlug
  branchSlug=$(echo "${branch:-no-branch}" | tr '/' '-' | tr -cd 'a-zA-Z0-9-' | cut -c1-40)
  local outFile="${handoffDir}/${ts}-auto-${branchSlug}.md"

  # Last real user prompts (strip command wrappers + system-reminder noise).
  local lastPrompts
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
  local lastTools
  lastTools=$(jq -rc '
    select(.type=="assistant")
    | .message.content[]?
    | select(.type=="tool_use")
    | "\(.name): \((.input | tostring)[0:140])"
  ' "$transcriptPath" 2>/dev/null | tail -20)

  # Active files: dedup file paths from Read/Edit/Write tool inputs.
  local activeFiles
  activeFiles=$(jq -r '
    select(.type=="assistant")
    | .message.content[]?
    | select(.type=="tool_use")
    | select(.name=="Read" or .name=="Edit" or .name=="Write")
    | .input.file_path // empty
  ' "$transcriptPath" 2>/dev/null | awk '!seen[$0]++' | tail -15)

  # Suggested skills — keyword heuristic over the last prompts.
  local skills="" promptsLower
  promptsLower=$(echo "$lastPrompts" | tr '[:upper:]' '[:lower:]')
  echo "$promptsLower" | grep -qE '(failing test|tdd|red.green|test.first)' && skills+="- tdd"$'\n'
  echo "$promptsLower" | grep -qE '(bug|broken|crash|fail|error|regress)' && skills+="- diagnose / why-failing"$'\n'
  echo "$promptsLower" | grep -qE '(scope|ticket|brief)' && skills+="- scope"$'\n'
  echo "$promptsLower" | grep -qE '(ship|pr |pull request|create-pr)' && skills+="- ship"$'\n'
  echo "$promptsLower" | grep -qE '(review|feedback|address)' && skills+="- address-feedback"$'\n'
  [[ -z "$skills" ]] && skills="- (none inferred)"

  {
    echo "# Auto-handoff — session ${sessionId:0:8} @ turn ${current} (ctx ${ctxTokens} tok)"
    echo ""
    echo "Generated mechanically by the handoff hooks (trigger: **${trigger}**) — live state is at risk of being \`/clear\`ed away. Treat verbatim sections as the primary source — the structure is a dump, not a summary."
    echo ""
    echo "**CWD:** \`${cwd:-?}\`  "
    echo "**Branch:** \`${branch:-?}\`  "
    echo "**Turn:** ${current}  "
    echo "**Context tokens:** ${ctxTokens}  "
    echo "**UTC:** ${ts}"
    echo ""
    echo "## Suggested skills for next session"
    echo ""
    echo "_Hints on HOW to do the work — not a directive to spawn a lane. Resume continues inline; never run \`wt\`/\`pickup\`/\`epic\` off these._"
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

  echo "$outFile"
}
