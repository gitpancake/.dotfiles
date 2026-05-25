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

input=$(cat)

toolName=$(jq -r '.tool_name // empty' <<<"$input")
case "$toolName" in
  Edit|Write|NotebookEdit|MultiEdit) ;;
  *) exit 0 ;;
esac

target=$(jq -r '.tool_input.file_path // .tool_input.notebook_path // empty' <<<"$input")
[[ -z "$target" ]] && exit 0

cwd=$(jq -r '.cwd // empty' <<<"$input")
[[ -z "$cwd" ]] && cwd=$PWD

# Linked-worktree check. In a linked worktree git-dir is <main>/.git/worktrees/<lane>
# while git-common-dir is <main>/.git — they differ. In the main checkout (or a
# bare/standalone repo) they're equal → not a lane, nothing to guard.
gitDir=$(git -C "$cwd" rev-parse --absolute-git-dir 2>/dev/null) || exit 0
commonDir=$(git -C "$cwd" rev-parse --git-common-dir 2>/dev/null) || exit 0
case "$commonDir" in
  /*) ;;                                   # already absolute
  *)  commonDir="$cwd/$commonDir" ;;       # relative form → anchor to cwd
esac
commonDir=$(cd "$commonDir" 2>/dev/null && pwd -P) || exit 0
[[ "$gitDir" == "$commonDir" ]] && exit 0  # not a linked worktree

# main_root = parent of the common .git ; wt_root = this lane's top level.
mainRoot=$(dirname "$commonDir")
wtRoot=$(git -C "$cwd" rev-parse --show-toplevel 2>/dev/null) || exit 0

# Canonicalize the target without requiring it to exist (Write creates files).
abs=$(python3 - "$target" "$cwd" <<'PY'
import os, sys
target, cwd = sys.argv[1], sys.argv[2]
if not os.path.isabs(target):
    target = os.path.join(cwd, target)
print(os.path.realpath(target))
PY
) || exit 0

# Trailing-slash prefixes so /repo doesn't match /repo-foo.
under() { case "$1/" in "$2"/*) return 0 ;; *) return 1 ;; esac; }

# Inside the lane → fine. Outside the main checkout entirely → fine (tickets,
# /tmp, home dotfiles). Only the in-main-but-out-of-lane band is the leak.
under "$abs" "$wtRoot" && exit 0
under "$abs" "$mainRoot" || exit 0

cat >&2 <<EOF
🚧 WORKTREE WRITE LEAK BLOCKED — this write escapes your lane.

  target : ${abs}
  lane   : ${wtRoot}
  main   : ${mainRoot}

You are in a wt worktree but the path points into the main checkout (or another
lane). Writing here pollutes main's working tree while your branch looks clean —
the exact cwd→main leak. Re-target the SAME relative path under your lane:

  ${wtRoot}/<relative/path>

Build paths from \$PWD / the worktree root, never the main repo's absolute path.
EOF
exit 2
