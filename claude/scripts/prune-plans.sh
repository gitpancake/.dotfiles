#!/bin/bash
# Prunes Claude plan files older than 2 days from both ~/.claude/plans/
# and the Obsidian vault mirror.

LOG="$HOME/.claude/logs/plan-prune.log"
OBSIDIAN="${CLAUDE_OBSIDIAN_PLANS_DIR:-$HOME/Documents/obsidian-vault/Henry Vault/04-PROJECTS/Claude Plans}"

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
  prune "$OBSIDIAN"
  prune "$OBSIDIAN/Agent Outputs"
  date "+%Y-%m-%d %H:%M:%S plan-prune complete"
} | tee -a "$LOG"
