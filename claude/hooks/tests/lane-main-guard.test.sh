#!/usr/bin/env bash
# Fixture for lane-main-guard.sh. Run: bash ~/.claude/hooks/tests/lane-main-guard.test.sh
set -u
hook=~/.claude/hooks/lane-main-guard.sh
lane=/Users/henrypye/Documents/code/cartage-agent/.claude/worktrees/some-lane
cockpit=/Users/henrypye/Documents/code/cartage-agent
fails=0

run() {
  local want=$1 name=$2 cwd=$3 cmd=$4
  local out verdict
  out=$(jq -n --arg c "$cmd" --arg d "$cwd" '{tool_name:"Bash",tool_input:{command:$c},cwd:$d}' | WT_TYPE= bash "$hook")
  verdict=$(jq -r '.hookSpecificOutput.permissionDecision // "allow"' <<<"${out:-{\}}")
  if [[ "$verdict" == "$want" ]]; then echo "ok    $name"; else echo "FAIL  $name (want $want, got $verdict)"; fails=$((fails+1)); fi
}

run deny  'lane checkout main'                 "$lane" 'git checkout main && git pull --ff-only && git log --oneline -3'
run deny  'lane cd then checkout main'         "$lane" "cd $lane && git checkout main"
run deny  'lane switch main'                   "$lane" 'git switch main'
run deny  'lane checkout -q main'              "$lane" 'git checkout -q main'
run deny  'lane checkout -f main'              "$lane" 'git checkout --force main'
run deny  'lane git -C checkout main'          "$lane" "git -C $lane checkout main; git pull"
run deny  'lane checkout main at end'          "$lane" 'git fetch origin && git checkout main'

run allow 'lane checkout -b from main'         "$lane" 'git checkout -b fix/thing main'
run allow 'lane switch -c from main'           "$lane" 'git switch -c fix/thing main'
run allow 'lane detached origin/main'          "$lane" 'git checkout --detach origin/main'
run allow 'lane rebase onto origin/main'       "$lane" 'git fetch origin && git rebase origin/main'
run allow 'lane checkout main-ish branch'      "$lane" 'git checkout maintenance/x'
run allow 'lane checkout file from main'       "$lane" 'git checkout origin/main -- src/x.ts'
run allow 'lane show main path'                "$lane" 'git show origin/main:package.json'
run allow 'lane non-git mention of main'       "$lane" 'grep -rn "checkout main" docs/'
run allow 'cockpit checkout main'              "$cockpit" 'git checkout main && git pull --ff-only'

echo; [[ $fails -eq 0 ]] && echo "all passed" || { echo "$fails failed"; exit 1; }
