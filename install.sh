#!/usr/bin/env bash
set -euo pipefail

DOTFILES_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Installing dotfiles from $DOTFILES_DIR"

# Zsh
ln -sf "$DOTFILES_DIR/zsh/.zshrc" ~/.zshrc
mkdir -p ~/.oh-my-zsh/custom/themes
ln -sf "$DOTFILES_DIR/zsh/robbyrussell-bar.zsh-theme" ~/.oh-my-zsh/custom/themes/robbyrussell-bar.zsh-theme
echo "  Linked zsh config and theme"

# Claude Code
mkdir -p ~/.claude
ln -sf "$DOTFILES_DIR/claude/statusline-command.sh" ~/.claude/statusline-command.sh
ln -sf "$DOTFILES_DIR/claude/settings.json" ~/.claude/settings.json
ln -sf "$DOTFILES_DIR/claude/CLAUDE.md" ~/.claude/CLAUDE.md
mkdir -p ~/.claude/hooks
ln -sf "$DOTFILES_DIR/claude/hooks/tmux-bell.sh" ~/.claude/hooks/tmux-bell.sh
mkdir -p ~/.claude/commands
for f in "$DOTFILES_DIR/claude/commands/"*.md; do
  ln -sf "$f" ~/.claude/commands/"$(basename "$f")"
done
mkdir -p ~/.claude/agents
for f in "$DOTFILES_DIR/claude/agents/"*.md; do
  ln -sf "$f" ~/.claude/agents/"$(basename "$f")"
done
echo "  Linked Claude Code config"

# tmux
ln -sf "$DOTFILES_DIR/tmux/.tmux.conf" ~/.tmux.conf
mkdir -p ~/.tmux
ln -sf "$DOTFILES_DIR/tmux/tmux-status.sh" ~/.tmux/tmux-status.sh
echo "  Linked tmux config"

echo "Done! Run 'source ~/.zshrc' to reload."
