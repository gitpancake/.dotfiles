#!/usr/bin/env bash
# PreToolUse hook: block the wt-lane "cwd→main" write leak.
#
# Symptom (seen repeatedly): a lane runs with cwd inside its worktree, but an
# Edit/Write fires with an ABSOLUTE path rooted at the main checkout (or a
# sibling lane's worktree). The edit lands outside the lane — polluting main's
# working tree or another branch — while the lane's own branch looks clean.
# grep returns worktree-relative hits, Edit writes main-absolute paths, and the
# mismatch only surfaces after `git checkout main` shows dirty src/.
#
# Guard contract:
#   - Only engages for file-writing tools (Edit/Write/NotebookEdit/MultiEdit).
#   - Only engages when cwd is a LINKED worktree (git-dir != git-common-dir).
#     Normal main-repo sessions and non-repo cwds pass untouched.
#   - Blocks (exit 2) a write whose canonical target is under the main checkout
#     but NOT under the current worktree — i.e. it escaped the lane. Sibling
#     worktrees (also under main/.claude/worktrees) are caught for free.
#   - Everything else passes: relative paths (resolve under the worktree),
#     ~/.claude/tickets brief edits, /tmp scratch, etc.
#
# Block via exit 2 → stderr is surfaced back to Claude as the correction.

set -u
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/_guard.sh"

check_worktree_write() {
  case "$GUARD_TOOL" in
    Edit|Write|NotebookEdit|MultiEdit) ;;
    *) return 0 ;;
  esac
  [[ -z "$GUARD_FILE_PATH" ]] && return 0

  local gitDir commonDir mainRoot wtRoot abs
  gitDir=$(git -C "$GUARD_CWD" rev-parse --absolute-git-dir 2>/dev/null) || return 0
  commonDir=$(git -C "$GUARD_CWD" rev-parse --git-common-dir 2>/dev/null) || return 0
  [[ "$commonDir" != /* ]] && commonDir="$GUARD_CWD/$commonDir"
  commonDir=$(cd "$commonDir" 2>/dev/null && pwd -P) || return 0
  local isLinkedWorktree=false
  [[ "$gitDir" != "$commonDir" ]] && isLinkedWorktree=true
  $isLinkedWorktree || return 0

  mainRoot=$(dirname "$commonDir")
  wtRoot=$(git -C "$GUARD_CWD" rev-parse --show-toplevel 2>/dev/null) || return 0
  abs=$(python3 -c 'import os,sys; t,c=sys.argv[1:3]; print(os.path.realpath(t if os.path.isabs(t) else os.path.join(c,t)))' \
    "$GUARD_FILE_PATH" "$GUARD_CWD") || return 0

  isUnder() { case "$1/" in "$2"/*) return 0 ;; *) return 1 ;; esac; }
  isUnder "$abs" "$wtRoot" && return 0
  isUnder "$abs" "$mainRoot" || return 0

  guard_block "🚧 WORKTREE WRITE LEAK BLOCKED — this write escapes your lane.

  target : ${abs}
  lane   : ${wtRoot}
  main   : ${mainRoot}

You are in a wt worktree but the path points into the main checkout (or another
lane). Writing here pollutes main's working tree while your branch looks clean —
the exact cwd→main leak. Re-target the SAME relative path under your lane:
  ${wtRoot}/<relative/path>
Build paths from \$PWD / the worktree root, never the main repo's absolute path."
}

[[ "${BASH_SOURCE[0]}" == "$0" ]] && guard_main check_worktree_write
