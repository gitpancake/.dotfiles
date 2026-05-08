#!/usr/bin/env bash
# Notification hook: agent paused, needs human input.
# Sibling: tmux-bell.sh (visual bell). Both fire on Notification.

set -u

source "$HOME/.claude/hooks/_state-write.sh"

input=$(cat 2>/dev/null || true)
msg=$(printf '%s' "$input" | jq -r '.message // "input"' 2>/dev/null || echo "input")
short=$(printf '%s' "$msg" | tr -d '\n' | cut -c1-12)

write_state "WAITING:$short"
exit 0
