#!/usr/bin/env bash
# PreToolUse hook: block the tail-pipe hang recipes before they start.
#
# Why a hook and not prose: ~/.claude/CLAUDE.md (Shell Gotchas) and
# lane-protocol.md ban `cmd | tail -N` on long commands, and lanes kept
# shipping it (2026-09-01 on checks; 2026-09-15 on `bun run script … | tail -40`,
# 2.5 min of zero output). Permission rules can't match mid-command pipes
# (prefix-only), so this is the mechanical layer.
#
# Denies (not asks — lanes run --dangerously-skip-permissions, a prompt would
# hang them):
#   1. `tail -f` / `tail -F` / `--follow` anywhere — never exits, the Bash tool
#      can only time out on it. Read the file with tail -N in a bounded loop.
#   2. Any backgrounded command piped into tail/head — the exact hang: the
#      background wrapper holds the pipe's write end open, tail never sees EOF.
#   3. Any app-process runner (bun/bunx/node/npx/tsx/npm/pnpm/yarn, tsc,
#      vitest, jest, next) piped into tail/head — tail buffers until EOF, so
#      the lane sees nothing while the app boots, the timeout fires, the
#      command auto-backgrounds, and case 2 takes over.
#   4. A check/build command (bun test, type-check, tsc, vitest, jest, next
#      build) backgrounded at all — lane-protocol.md: checks run plain
#      foreground; big output goes to a file, then grep it.
#
# Fast CLIs (git, gh, ls, grep, jq …) piped into head/tail stay allowed.

set -u

input=$(cat)

[[ "$(jq -r '.tool_name // empty' <<<"$input")" == "Bash" ]] || exit 0

cmd=$(jq -r '.tool_input.command // empty' <<<"$input")
[[ -z "$cmd" ]] && exit 0

in_background=$(jq -r '.tool_input.run_in_background // false' <<<"$input")

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

if grep -Eq '(^|[[:space:];&|(])tail([[:space:]]+[^|;&]*)?[[:space:]]+(-[a-zA-Z]*[fF][a-zA-Z]*|--follow)([[:space:]=]|$)' <<<"$cmd"; then
  deny "tail -f never exits, so the Bash tool can only time out on it (~/.claude/CLAUDE.md Shell Gotchas). Read the log with a bounded loop instead: for i in {1..N}; do tail -n 40 <file>; grep -q '<done marker>' <file> && break; sleep 10; done — or just tail -n 40 <file> once per check."
fi

pipesToTail=false
grep -Eq '\|[[:space:]]*(tail|head)([[:space:]]|$)' <<<"$cmd" && pipesToTail=true

if [[ "$in_background" == "true" && "$pipesToTail" == "true" ]]; then
  deny "Backgrounded pipe into tail/head hangs after the real command exits (pipe write end stays open, no EOF — Shell Gotchas, ~/.claude/CLAUDE.md). Background the bare command with no trailing pipe and read its output file, or redirect to a file and tail the file in a separate call."
fi

isAppProcess=false
grep -Eq '(^|[[:space:];&|(])(bun|bunx|node|npx|tsx|npm|pnpm|yarn|tsc|vitest|jest|next)([[:space:]]|$)' <<<"$cmd" && isAppProcess=true

if [[ "$isAppProcess" == "true" && "$pipesToTail" == "true" ]]; then
  deny "Never pipe an app process (bun run script, bun test, node, …) into tail/head (Shell Gotchas, ~/.claude/CLAUDE.md): tail buffers until EOF so you see nothing while it runs, the timeout fires, the command auto-backgrounds, and the pipe hangs forever. Run it plain foreground; output too big → cmd > out.log 2>&1, then grep/tail the file in a separate call."
fi

isCheckCmd=false
grep -Eq 'bun +(run +)?(test|type-check|build)|tsc([[:space:]]|$)|vitest|jest([[:space:]]|$)|next +build' <<<"$cmd" && isCheckCmd=true

if [[ "$isCheckCmd" == "true" && "$in_background" == "true" ]]; then
  deny "Checks run plain foreground, never run_in_background (lane-protocol.md) — the spawn/poll scaffolding costs more wall-clock than the check itself. Run it as one foreground command."
fi

exit 0
