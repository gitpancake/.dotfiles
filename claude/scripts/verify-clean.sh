#!/usr/bin/env bash
# verify-clean.sh [<wt-path>]
#
# Remove the verify gate state (verify.ok and verify.log) for a lane,
# so the next verifier subagent run starts clean.
#
# Default target: $PWD. Pass an explicit worktree root to clean a different lane.

set -u

target=${1:-$PWD}

if [ ! -d "$target" ]; then
  printf 'verify-clean: not a directory: %s\n' "$target" >&2
  exit 2
fi

claude_dir="$target/.claude"

if [ ! -d "$claude_dir" ]; then
  printf 'verify-clean: no .claude/ in %s — nothing to clean\n' "$target"
  exit 0
fi

removed=0
for f in verify.ok verify.log; do
  path="$claude_dir/$f"
  if [ -e "$path" ]; then
    rm -f "$path"
    printf 'removed %s\n' "$path"
    removed=$((removed + 1))
  fi
done

if (( removed == 0 )); then
  printf 'verify-clean: nothing to remove in %s\n' "$claude_dir"
fi
