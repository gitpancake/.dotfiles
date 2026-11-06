#!/usr/bin/env bash
# Golden-output harness for the PreToolUse guards. Prints one line per case:
# <case#> <exit> <output>. `bash guard-cases.sh <hook-or-dispatcher>` runs one
# hook over every case; diff two runs to prove a refactor changed nothing.
set -u

hook=$1
lane=$(ls -d "$HOME"/Documents/code/cartage-agent/.claude/worktrees/*/ 2>/dev/null | head -n 1)
lane=${lane%/}
cockpit=$HOME/Documents/code/cartage-agent

emitCase() {
  jq -nc --arg t "$1" --arg c "$2" --arg cwd "$3" --argjson bg "$4" --arg fp "$5" \
    '{tool_name:$t, tool_input:({command:$c, run_in_background:$bg} + (if $fp == "" then {} else {file_path:$fp} end)),
      cwd:$cwd, session_id:"golden", transcript_path:"/dev/null"}'
}

bashCommands=(
  "ls -la"
  "git checkout main"
  "git switch -q main"
  "tail -f x.log"
  "bun test x | tail -5"
  "bun type-check"
  "gh pr checks 1"
  "gh pr view 1 --json statusCheckRollup"
  "gh pr view 1 --json body"
  "sleep 60"
  "sleep 5 && ls"
  "until curl x; do sleep 45; done"
  "devin-review.sh gate https://x"
  "devin-review.sh status x"
  "sleep 90 && gh pr view 1"
  "psql \$URL -c 'set statement_timeout=0'"
  "psql postgres://u@ep-x-pooler.us-east-2.aws.neon.tech/db -c 'SET search_path to x'"
  "vercel env pull"
  "node x.js agent-database-production '.set('"
  "gcloud firestore import gs://x"
  "for i in 1 2; do gh pr checks 1; done"
)

caseNumber=0
runCase() {
  caseNumber=$((caseNumber + 1))
  local out exitCode
  out=$(emitCase "$@" | WT_TYPE= bash "$hook" 2>&1)
  exitCode=$?
  printf '%s\t%s\t%s\n' "$caseNumber" "$exitCode" "$(printf '%s' "$out" | tr '\n' ' ' | cut -c1-400)"
}

for cwd in "$lane" "$cockpit"; do
  for cmd in "${bashCommands[@]}"; do
    runCase Bash "$cmd" "$cwd" false ""
  done
  runCase Bash "bun test x" "$cwd" true ""
  runCase Bash "bun dev | tail -3" "$cwd" true ""
  runCase Edit "" "$cwd" false "$cockpit/src/x.ts"
  runCase Edit "" "$cwd" false "$lane/src/x.ts"
  runCase Read "" "$cwd" false "$cockpit/src/x.ts"
done
