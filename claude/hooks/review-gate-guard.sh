#!/usr/bin/env bash
# PreToolUse hook: in a lane, the review loop is ONE call — `devin-review.sh gate`.
#
# Why a hook and not prose: ~/.claude/CLAUDE.md and lane-protocol.md both said
# "gate, never status+sleep", and PR #8665's lane still ran 16 `status` calls and
# 11 `sleep 90 &&` polls, read one issue comment, and missed every Devin/Greptile
# finding until they were pasted in by hand. Prose shaped nothing. The hand-rolled
# loop also returns the arbiter's push-time verdict, which predates the reviewers.
#
# Also denies a FOREGROUND gate: it waits up to ~9 min on remote reviewers, and a
# foreground Bash call freezes the lane so the cockpit cannot send follow-ups.
# Lanes run the gate through the Monitor tool: claude-lane disables background
# tasks, so a lane's Bash tool rejects `run_in_background` outright.
#
# Denies (not asks — lanes run --dangerously-skip-permissions, a prompt would
# hang them). Cockpit sessions pass untouched.

set -u
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/_guard.sh"

check_review_gate() {
  guard_is_bash || return 0
  $GUARD_IS_LANE || return 0
  local cmd=$GUARD_CMD

  local gateHint='NOTHING in this command ran — a denied call executes no part of it, so if it began with `git push`, the push did NOT happen and your commit is still local. Re-run as exactly ONE call through the Monitor tool (ToolSearch "select:Monitor"; a lane Bash tool has no run_in_background), timeout_ms 900000: `cd <worktree> && git push && ~/.claude/scripts/devin-review.sh gate "<PR url>"; echo GATE_EXIT=$?` — it triggers, waits for a SETTLED arbiter verdict (newer than every reviewer post on the head sha), and prints every finding. Running `gate` without the push polls the OLD sha. `devin-review.sh findings "<PR url>"` re-prints findings without waiting. (lane-protocol.md §Review loop)'

  if grep -Eq 'devin-review\.sh[[:space:]]+gate([[:space:]]|$)' <<<"$cmd" && [[ "$GUARD_IS_BACKGROUND" != "true" ]]; then
    guard_deny "A foreground gate freezes this lane for up to ~9 min and blocks follow-up messages from the cockpit. $gateHint"
  fi

  if grep -Eq 'devin-review\.sh[[:space:]]+(status|trigger|wait)([[:space:]]|$)' <<<"$cmd"; then
    guard_deny "devin-review.sh status/trigger/wait are cockpit tools. $gateHint"
  fi

  if grep -Eq 'sleep[[:space:]]+[0-9]+[[:space:]]*(&&|;).*(devin-review|/status|/statuses|arbiter|pr checks|pr view)' <<<"$cmd"; then
    guard_deny "Hand-rolled sleep+poll burns a full-context turn per tick and reads the arbiter's push-time verdict, which predates Devin/Greptile. $gateHint"
  fi

  if grep -Eq 'gh[[:space:]]+pr[[:space:]]+checks([[:space:]]|$)' <<<"$cmd"; then
    guard_deny "gh pr checks is a status poll (365 lane calls in the 7 days to 2026-11-06). CI state is part of what the gate settles on and prints. $gateHint"
  fi

  if grep -Eq 'gh[[:space:]]+pr[[:space:]]+view.*(statusCheckRollup|reviewDecision|latestReviews|reviews|mergeStateStatus)' <<<"$cmd"; then
    guard_deny "Reading review or check state with gh pr view is a hand-rolled poll; the gate prints the settled verdict and every finding. $gateHint"
  fi

  local longSleep
    longSleep=$(grep -Eo '(^|[[:space:];&|(])sleep[[:space:]]+[0-9]+' <<<"$cmd" | grep -Eo '[0-9]+$' | sort -n | tail -1)
  if [[ -n "$longSleep" ]] && (( longSleep >= 30 )); then
    guard_deny "sleep ${longSleep} blocks the lane and each wake is a full-context turn (527 lane sleeps in the 7 days to 2026-11-06). Waiting on a condition (VM boot, a deploy, a file) → ONE Monitor call with an until-loop that checks the condition and sleeps inside the loop. Waiting on review → $gateHint"
  fi

  if grep -Eq '(^|[[:space:];&|(])(for|until|while)[[:space:]].*(devin-review\.sh|commits/[^[:space:]]+/status|gh pr checks)' <<<"$cmd"; then
    guard_deny "Loop-polling review state is what the gate does internally, with settle detection. $gateHint"
  fi
}

[[ "${BASH_SOURCE[0]}" == "$0" ]] && guard_main check_review_gate
