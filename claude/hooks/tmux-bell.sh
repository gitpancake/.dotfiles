#!/usr/bin/env bash
# Notification hook: raise tmux's bell flag on the lane's own window so the tab
# paints in window-status-bell-style until visited.
#
# A BEL to stdout never reaches the terminal here — hook and tool output is
# captured by Claude Code — so the BEL goes straight to the pane's tty.
# Resolution order: the lane's stamped window label (survives a cockpit-owned
# TMUX_PANE), then the pane this hook inherited.

[[ -n "${TMUX:-}" ]] || exit 0

dir="${CLAUDE_PROJECT_DIR:-$PWD}"
win=""
if [[ -f "$dir/.claude/tmux-window" ]]; then
  label=$(head -n1 "$dir/.claude/tmux-window")
  win=$(tmux list-windows -a -F '#{window_id} #{window_name}' 2>/dev/null \
    | awk -v l="$label" '$2 == l { print $1; exit }')
fi
if [[ -z "$win" && -n "${TMUX_PANE:-}" ]]; then
  win=$(tmux display-message -t "$TMUX_PANE" -p '#{window_id}' 2>/dev/null)
fi
[[ -n "$win" ]] || exit 0

tty=$(tmux list-panes -t "$win" -F '#{pane_tty}' 2>/dev/null | head -n1)
[[ -n "$tty" && -w "$tty" ]] && printf '\a' > "$tty"
exit 0
