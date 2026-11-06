#!/usr/bin/env bash
# Shared skeleton for PreToolUse guards. A guard file defines one function,
# check_<name>, that reads the GUARD_* context and either returns (allow) or
# calls guard_deny / guard_ask / guard_block, which print the decision and
# exit. Run standalone, a guard ends with `guard_main check_<name>`; run under
# hook-dispatch.sh, every enabled check shares one parsed input and the first
# decision ends the chain.

guard_read_input() {
  GUARD_INPUT=$(cat)
  eval "$(jq -r '@sh "
    GUARD_TOOL=\(.tool_name // "")
    GUARD_CMD=\(.tool_input.command // "")
    GUARD_FILE_PATH=\(.tool_input.file_path // .tool_input.notebook_path // "")
    GUARD_IS_BACKGROUND=\(.tool_input.run_in_background // false)
    GUARD_CWD=\(.cwd // "")
    GUARD_SESSION_ID=\(.session_id // "")
    GUARD_TRANSCRIPT=\(.transcript_path // "")
  "' <<<"$GUARD_INPUT")"
  [[ -z "$GUARD_CWD" ]] && GUARD_CWD=$PWD
  GUARD_IS_LANE=false
  [[ "$GUARD_CWD" == */.claude/worktrees/* || -n "${WT_TYPE:-}" ]] && GUARD_IS_LANE=true
  return 0
}

guard_decide() {
  jq -n --arg d "$1" --arg r "$2" '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: $d,
      permissionDecisionReason: $r
    }
  }'
  exit 0
}

guard_deny() { guard_decide deny "$1"; }
guard_ask() { guard_decide ask "$1"; }

guard_block() {
  printf '%s\n' "$1" >&2
  exit 2
}

guard_is_bash() { [[ "$GUARD_TOOL" == "Bash" && -n "$GUARD_CMD" ]]; }

guard_main() {
  guard_read_input
  "$1"
  exit 0
}
