#!/usr/bin/env bash
set -euo pipefail

DOTFILES_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Installing dotfiles (macOS) from $DOTFILES_DIR"

# --- Check / install dependencies ---

# Homebrew
if ! command -v brew &>/dev/null; then
  echo "  Installing Homebrew..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  eval "$(/opt/homebrew/bin/brew shellenv zsh 2>/dev/null || /usr/local/bin/brew shellenv zsh)"
else
  echo "  Homebrew: already installed"
fi

# tmux
if ! command -v tmux &>/dev/null; then
  echo "  Installing tmux..."
  brew install tmux
else
  echo "  tmux: already installed"
fi

# Oh My Zsh
if [ ! -d "$HOME/.oh-my-zsh" ]; then
  echo "  Installing Oh My Zsh..."
  sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" "" --unattended
else
  echo "  Oh My Zsh: already installed"
fi

# nvm
if [ ! -d "$HOME/.nvm" ]; then
  echo "  Installing nvm..."
  curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
else
  echo "  nvm: already installed"
fi

# --- Link dotfiles ---

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

echo ""
echo "Done! Run 'source ~/.zshrc' to reload."
