#!/usr/bin/env bash
set -euo pipefail

DOTFILES_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Installing dotfiles from $DOTFILES_DIR"

source "$DOTFILES_DIR/_link-dotfiles.sh"
echo "  Linked dotfiles"

echo "Done! Run 'source ~/.zshrc' to reload."
