# CLAUDE.md

## Project Overview

Personal dotfiles repository for macOS and WSL2 (Ubuntu) development environments. Managed with symlinks via `install.sh` (Linux/WSL2) or `install-mac.sh` (macOS).

## Structure

- `zsh/.zshrc` - Main zsh configuration (Oh My Zsh, nvm, brew, aliases)
- `zsh/robbyrussell-bar.zsh-theme` - Custom Oh My Zsh theme with battery/time status bar
- `claude/settings.json` - Claude Code settings and enabled plugins
- `claude/statusline-command.sh` - Script powering Claude Code's bottom status line
- `claude/CLAUDE.md` - Global instructions (thin coordination layer — workflow rules, agent routing, OV protocol)
- `claude/commands/` - Specialized agent profiles invoked as `/backend`, `/frontend`, `/database`, `/platform`, `/fullstack`
- `tmux/.tmux.conf` - tmux config with intuitive pane/window keybindings and gruvbox dark theme
- `tmux/tmux-status.sh` - tmux status bar script showing battery, CPU, memory, disk with dynamic color-coded thresholds (green → yellow → orange → red)
- `install.sh` - Symlink installer for Linux/WSL2 systems
- `install-mac.sh` - Symlink installer for macOS systems

## Key Details

- Target systems: macOS (uses `pmset` for battery info) and WSL2/Linux (uses `/sys/class/power_supply/BAT1/capacity`)
- Zsh theme uses `add-zsh-hook precmd` to print the status bar (not PROMPT, to avoid cursor issues)
- Claude status line script caches slow operations and keys session timers by `$PPID`
- Install scripts use `ln -sf` to create symlinks — editing files in this repo updates the live config

## Editing Guidelines

- After changing zsh files, test with `zsh -n <file>` for syntax errors
- Keep the status line script fast — it runs on every Claude Code refresh
- The tmux status script also needs to stay fast — it runs every 5 seconds (`status-interval 5`)
- tmux color thresholds: 0-25% green, 26-50% yellow, 51-75% orange, 76-100% red (battery inverted)
- The `.zshrc` has a duplicate `brew shellenv` line (line 116-118) — this is harmless but could be cleaned up
