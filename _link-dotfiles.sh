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
mkdir -p ~/.claude ~/.claude/hooks ~/.claude/commands ~/.claude/agents ~/.claude/skills ~/.claude/logs
ln -sf "$DOTFILES_DIR/claude/statusline-command.sh" ~/.claude/statusline-command.sh
ln -sf "$DOTFILES_DIR/claude/transcript-costs.sh" ~/.claude/transcript-costs.sh
ln -sf "$DOTFILES_DIR/claude/settings.json" ~/.claude/settings.json
ln -sf "$DOTFILES_DIR/claude/CLAUDE.md" ~/.claude/CLAUDE.md
ln -sf "$DOTFILES_DIR/claude/worktree-protocol.md" ~/.claude/worktree-protocol.md
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

# tmux
mkdir -p ~/.tmux
ln -sf "$DOTFILES_DIR/tmux/.tmux.conf" ~/.tmux.conf
ln -sf "$DOTFILES_DIR/tmux/tmux-status.sh" ~/.tmux/tmux-status.sh
ln -sf "$DOTFILES_DIR/tmux/agent-board.sh" ~/.tmux/agent-board.sh
[ -f "$DOTFILES_DIR/tmux/grid-4x2.sh" ] && ln -sf "$DOTFILES_DIR/tmux/grid-4x2.sh" ~/.tmux/grid-4x2.sh

# vim
ln -sf "$DOTFILES_DIR/vim/.vimrc" ~/.vimrc
