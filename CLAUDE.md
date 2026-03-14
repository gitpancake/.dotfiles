# CLAUDE.md

## Project Overview

Personal dotfiles repository for a WSL2 (Ubuntu) development environment. Managed with symlinks via `install.sh`.

## Structure

- `zsh/.zshrc` - Main zsh configuration (Oh My Zsh, nvm, brew, aliases)
- `zsh/robbyrussell-bar.zsh-theme` - Custom Oh My Zsh theme with battery/time status bar
- `claude/settings.json` - Claude Code settings and enabled plugins
- `claude/statusline-command.sh` - Script powering Claude Code's bottom status line
- `tmux/.tmux.conf` - tmux config with intuitive pane/window keybindings and gruvbox dark theme
- `tmux/tmux-status.sh` - tmux status bar script showing battery, CPU, memory, disk with dynamic color-coded thresholds (green → yellow → orange → red)
- `install.sh` - Symlink installer that links files to their expected locations

## Key Details

- Target system: WSL2 on Windows, battery info at `/sys/class/power_supply/BAT1/capacity`
- Zsh theme uses `add-zsh-hook precmd` to print the status bar (not PROMPT, to avoid cursor issues)
- Claude status line script caches slow operations and keys session timers by `$PPID`
- `install.sh` uses `ln -sf` to create symlinks — editing files in this repo updates the live config

## Editing Guidelines

- After changing zsh files, test with `zsh -n <file>` for syntax errors
- Keep the status line script fast — it runs on every Claude Code refresh
- The tmux status script also needs to stay fast — it runs every 5 seconds (`status-interval 5`)
- tmux color thresholds: 0-25% green, 26-50% yellow, 51-75% orange, 76-100% red (battery inverted)
- The `.zshrc` has a duplicate `brew shellenv` line (line 116-118) — this is harmless but could be cleaned up
