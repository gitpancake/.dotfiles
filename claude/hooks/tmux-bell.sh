#!/usr/bin/env bash
# Send bell to tmux pane so the tab flashes
if [ -n "$TMUX" ]; then
  printf '\a'
fi
