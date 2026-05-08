#!/usr/bin/env bash
# Pane renderer for slack-tldr. Designed for `watch -tcn2`.
# Header line + numbered active alerts below.

set -euo pipefail

dim()   { printf '\033[2m%s\033[0m' "$1"; }
bold()  { printf '\033[1m%s\033[0m' "$1"; }
red()   { printf '\033[31m%s\033[0m' "$1"; }
green() { printf '\033[32m%s\033[0m' "$1"; }

state_file="${SLACK_TLDR_STATE:-$HOME/.local/share/slack-tldr/state.json}"

if [ ! -f "$state_file" ]; then
  printf '%s  %s\n' "$(bold "slack alerts")" "$(dim "(daemon not running)")"
  exit 0
fi

count=$(python3 -c "
import json, sys
try:
    with open('$state_file') as f:
        d = json.load(f)
    print(len(d.get('active', [])))
except Exception:
    print(0)
")

if [ "$count" -eq 0 ]; then
  printf '%s  %s\n' "$(bold "slack alerts")" "$(green "clear")"
else
  printf '%s  %s\n' "$(bold "slack alerts")" "$(red "$count active")"
fi
echo

exec python3 "$HOME/.dotfiles/scripts/slack-tldr.py" pane
