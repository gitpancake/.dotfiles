#!/usr/bin/env bash
# Shared symlink setup — sourced by install.sh, install-mac.sh, rewire-symlinks.sh.
# Expects $DOTFILES_DIR to be set by the caller.
set -euo pipefail

# Zsh
ln -sf "$DOTFILES_DIR/zsh/.zshenv" ~/.zshenv
ln -sf "$DOTFILES_DIR/zsh/.zshrc" ~/.zshrc
mkdir -p ~/.oh-my-zsh/custom/themes
ln -sf "$DOTFILES_DIR/zsh/robbyrussell-bar.zsh-theme" ~/.oh-my-zsh/custom/themes/robbyrussell-bar.zsh-theme

# Claude Code
mkdir -p ~/.claude ~/.claude/hooks ~/.claude/commands ~/.claude/agents ~/.claude/skills ~/.claude/scripts ~/.claude/handoffs ~/.claude/logs
ln -sf "$DOTFILES_DIR/claude/statusline-command.sh" ~/.claude/statusline-command.sh
ln -sf "$DOTFILES_DIR/claude/transcript-costs.sh" ~/.claude/transcript-costs.sh
ln -sf "$DOTFILES_DIR/claude/settings.json" ~/.claude/settings.json
ln -sf "$DOTFILES_DIR/claude/CLAUDE.md" ~/.claude/CLAUDE.md
ln -sf "$DOTFILES_DIR/claude/worktree-protocol.md" ~/.claude/worktree-protocol.md
ln -sf "$DOTFILES_DIR/claude/mcp.lane.json" ~/.claude/mcp.lane.json
# lane-bin: PATH-shim dir for slow build tools (bun → timeout-wrapped).
# Prepended to PATH inside claude-lane only — doesn't affect normal shells.
chmod +x "$DOTFILES_DIR/claude/lane-bin/"* 2>/dev/null || true
ln -sfn "$DOTFILES_DIR/claude/lane-bin" ~/.claude/lane-bin
for f in "$DOTFILES_DIR/claude/hooks/"*.sh; do
  chmod +x "$f"
  ln -sf "$f" ~/.claude/hooks/"$(basename "$f")"
done
for f in "$DOTFILES_DIR/claude/commands/"*.md; do
  ln -sf "$f" ~/.claude/commands/"$(basename "$f")"
done
for f in "$DOTFILES_DIR/claude/agents/"*.md; do
  ln -sf "$f" ~/.claude/agents/"$(basename "$f")"
done
# skills are directories (SKILL.md + supporting files) — link each dir
for d in "$DOTFILES_DIR/claude/skills/"*/; do
  [ -d "$d" ] || continue
  ln -sfn "${d%/}" ~/.claude/skills/"$(basename "$d")"
done
# bin scripts → ~/.local/bin (on PATH via .zshenv)
mkdir -p ~/.local/bin
for f in "$DOTFILES_DIR/claude/bin/"*; do
  [ -e "$f" ] || continue
  chmod +x "$f"
  ln -sf "$f" ~/.local/bin/"$(basename "$f")"
done
# claude/scripts → ~/.claude/scripts — referenced by absolute path from
# hooks and the TIX_PRELOAD_HOOK / WT_TICKET_SYNC env vars (e.g.
# ticket-status-sync.py, plan-lint.sh), so they must resolve at a stable
# location. Lane-orchestration scripts moved to the wt-lanes repo
# (github.com/gitpancake/wt-lanes) — its install.sh writes into the same
# ~/.claude/scripts/ namespace alongside the ones still here.
for f in "$DOTFILES_DIR/claude/scripts/"*; do
  [ -e "$f" ] || continue
  case "$f" in *.sh|*.py) chmod +x "$f" ;; esac
  ln -sf "$f" ~/.claude/scripts/"$(basename "$f")"
done

# Pi
mkdir -p ~/.pi/agent ~/.pi/agent/bin ~/.pi/agent/extensions ~/.pi/agent/prompts ~/.pi/agent/skills ~/.pi/agent/themes
ln -sf "$DOTFILES_DIR/pi/AGENTS.md" ~/.pi/agent/AGENTS.md
ln -sf "$DOTFILES_DIR/pi/settings.json" ~/.pi/agent/settings.json
ln -sf "$DOTFILES_DIR/pi/models.json" ~/.pi/agent/models.json
ln -sf "$DOTFILES_DIR/pi/keybindings.json" ~/.pi/agent/keybindings.json
for f in "$DOTFILES_DIR/pi/extensions/"*.ts "$DOTFILES_DIR/pi/extensions/"*.js; do
  [ -e "$f" ] || continue
  ln -sf "$f" ~/.pi/agent/extensions/"$(basename "$f")"
done
for f in "$DOTFILES_DIR/pi/prompts/"*.md; do
  [ -e "$f" ] || continue
  ln -sf "$f" ~/.pi/agent/prompts/"$(basename "$f")"
done
for d in "$DOTFILES_DIR/pi/skills/"*/; do
  [ -d "$d" ] || continue
  [ ! -L "${d%/}" ] || continue
  dest=~/.pi/agent/skills/"$(basename "$d")"
  rm -rf "$dest"
  ln -s "${d%/}" "$dest"
done
for f in "$DOTFILES_DIR/pi/themes/"*.json; do
  [ -e "$f" ] || continue
  ln -sf "$f" ~/.pi/agent/themes/"$(basename "$f")"
done
for f in "$DOTFILES_DIR/pi/bin/"*; do
  [ -e "$f" ] || continue
  chmod +x "$f"
  ln -sf "$f" ~/.pi/agent/bin/"$(basename "$f")"
done

# tmux
mkdir -p ~/.tmux
ln -sf "$DOTFILES_DIR/tmux/.tmux.conf" ~/.tmux.conf
ln -sf "$DOTFILES_DIR/tmux/tmux-status.sh" ~/.tmux/tmux-status.sh
# agent-board.sh moved out — owned by wt-lanes (github.com/gitpancake/wt-lanes).
# Install it via ~/Documents/code/wt-lanes/install.sh, which symlinks it into
# ~/.tmux/agent-board.sh.
[ -f "$DOTFILES_DIR/tmux/grid-4x2.sh" ] && ln -sf "$DOTFILES_DIR/tmux/grid-4x2.sh" ~/.tmux/grid-4x2.sh

# vim
ln -sf "$DOTFILES_DIR/vim/.vimrc" ~/.vimrc

# Ghostty (config dir created if missing — macOS cask install lives in install-mac.sh)
mkdir -p ~/.config/ghostty
ln -sf "$DOTFILES_DIR/ghostty/config" ~/.config/ghostty/config
