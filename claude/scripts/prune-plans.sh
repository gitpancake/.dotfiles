#!/bin/bash
# Prunes Claude plan files older than 2 days from ~/.claude/plans/.

LOG="$HOME/.claude/logs/plan-prune.log"

prune() {
  local dir="$1"
  local count
  count=$(find "$dir" -name "*.md" -mtime +2 2>/dev/null | wc -l | tr -d ' ')
  find "$dir" -name "*.md" -mtime +2 -delete 2>/dev/null
  echo "$count files pruned from $dir"
}

{
  date "+%Y-%m-%d %H:%M:%S plan-prune start"
  prune "$HOME/.claude/plans"
  date "+%Y-%m-%d %H:%M:%S plan-prune complete"
} | tee -a "$LOG"
