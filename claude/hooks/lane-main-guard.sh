#!/usr/bin/env bash
# PreToolUse hook: a lane never has `main` as its HEAD.
#
# Why a hook and not prose: on 2026-11-04 the users-flip lane ran
# `git checkout main && git pull --ff-only` inside its worktree to rerun a
# backfill against "PR1's merged state". That parked the shared `main` ref in a
# lane worktree, so the cockpit could no longer `git checkout main` ("'main' is
# already used by worktree ..."), and a lane commit from there would have been
# a commit on main. lane-protocol.md already said branch-only; prose shaped
# nothing.
#
# Denies (not asks — lanes run --dangerously-skip-permissions, a prompt would
# hang them) any `git checkout`/`git switch` whose target is `main` when the cwd
# is a lane worktree. Creating a branch FROM main (`checkout -b x main`,
# `switch -c x main`) and detached `origin/main` stay allowed. Cockpit sessions
# pass untouched.

set -u

input=$(cat)

[[ "$(jq -r '.tool_name // empty' <<<"$input")" == "Bash" ]] || exit 0

cmd=$(jq -r '.tool_input.command // empty' <<<"$input")
[[ -z "$cmd" ]] && exit 0

cwd=$(jq -r '.cwd // empty' <<<"$input")
[[ -z "$cwd" ]] && cwd=$PWD
isLane=false
[[ "$cwd" == */.claude/worktrees/* || -n "${WT_TYPE:-}" ]] && isLane=true
$isLane || exit 0

deny() {
  jq -n --arg r "$1" '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: $r
    }
  }'
  exit 0
}

checkoutToMain='git([[:space:]]+-C[[:space:]]+[^[:space:]]+)?[[:space:]]+(checkout|switch)([[:space:]]+(-q|--quiet|-f|--force|--detach|-d))*[[:space:]]+main([[:space:]]|$|[;&|)])'

if grep -Eq "$checkoutToMain" <<<"$cmd"; then
  deny 'NOTHING in this command ran. A lane never checks out `main`: the ref is shared with the cockpit and every other worktree, so parking it here blocks `git checkout main` everywhere else and turns your next commit into a commit on main. Stay on your lane branch. Need main'"'"'s content? Read it without moving HEAD: `git show origin/main:<path>`, `git diff origin/main -- <path>`, or `git worktree add <scratch-dir> --detach origin/main` and run there. Need main merged in? `git fetch origin && git rebase origin/main` (or `git merge origin/main`) on your branch. (lane-protocol.md)'
fi

exit 0
