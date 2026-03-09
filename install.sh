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
echo "  Linked Claude Code config"

echo "Done! Run 'source ~/.zshrc' to reload."
