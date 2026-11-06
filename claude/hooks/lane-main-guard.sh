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
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/_guard.sh"

check_lane_main() {
  guard_is_bash || return 0
  $GUARD_IS_LANE || return 0

  local checkoutToMain='git([[:space:]]+-C[[:space:]]+[^[:space:]]+)?[[:space:]]+(checkout|switch)([[:space:]]+(-q|--quiet|-f|--force|--detach|-d))*[[:space:]]+main([[:space:]]|$|[;&|)])'
  if grep -Eq "$checkoutToMain" <<<"$GUARD_CMD"; then
    guard_deny 'NOTHING in this command ran. A lane never checks out `main`: the ref is shared with the cockpit and every other worktree, so parking it here blocks `git checkout main` everywhere else and turns your next commit into a commit on main. Stay on your lane branch. Need main'"'"'s content? Read it without moving HEAD: `git show origin/main:<path>`, `git diff origin/main -- <path>`, or `git worktree add <scratch-dir> --detach origin/main` and run there. Need main merged in? `git fetch origin && git rebase origin/main` (or `git merge origin/main`) on your branch. (lane-protocol.md)'
  fi
}

[[ "${BASH_SOURCE[0]}" == "$0" ]] && guard_main check_lane_main
