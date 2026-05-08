#!/usr/bin/env bash
# Rewires all dotfile symlinks to point to ~/.dotfiles
set -euo pipefail
NEW="$HOME/.dotfiles"

# Zsh
ln -sf "$NEW/zsh/.zshenv" ~/.zshenv
ln -sf "$NEW/zsh/.zshrc" ~/.zshrc
mkdir -p ~/.oh-my-zsh/custom/themes
ln -sf "$NEW/zsh/robbyrussell-bar.zsh-theme" ~/.oh-my-zsh/custom/themes/robbyrussell-bar.zsh-theme
echo "  zsh: OK"

# Claude
ln -sf "$NEW/claude/statusline-command.sh" ~/.claude/statusline-command.sh
ln -sf "$NEW/claude/transcript-costs.sh" ~/.claude/transcript-costs.sh
ln -sf "$NEW/claude/settings.json" ~/.claude/settings.json
ln -sf "$NEW/claude/CLAUDE.md" ~/.claude/CLAUDE.md
ln -sf "$NEW/claude/worktree-protocol.md" ~/.claude/worktree-protocol.md
for f in "$NEW/claude/hooks/"*.sh; do ln -sf "$f" ~/.claude/hooks/"$(basename "$f")"; done
for f in "$NEW/claude/commands/"*.md; do ln -sf "$f" ~/.claude/commands/"$(basename "$f")"; done
for f in "$NEW/claude/agents/"*.md; do ln -sf "$f" ~/.claude/agents/"$(basename "$f")"; done
mkdir -p ~/.local/bin
for f in "$NEW/claude/bin/"*; do
  [ -e "$f" ] || continue
  chmod +x "$f"
  ln -sf "$f" ~/.local/bin/"$(basename "$f")"
done
echo "  claude: OK"

# tmux
ln -sf "$NEW/tmux/.tmux.conf" ~/.tmux.conf
mkdir -p ~/.tmux
ln -sf "$NEW/tmux/tmux-status.sh" ~/.tmux/tmux-status.sh
ln -sf "$NEW/tmux/agent-board.sh" ~/.tmux/agent-board.sh
[ -f "$NEW/tmux/grid-4x2.sh" ] && ln -sf "$NEW/tmux/grid-4x2.sh" ~/.tmux/grid-4x2.sh
echo "  tmux: OK"

# vim
ln -sf "$NEW/vim/.vimrc" ~/.vimrc
echo "  vim: OK"

# LaunchAgents
TRANSCRIPT_PLIST="$HOME/Library/LaunchAgents/local.claude-transcript-prune.plist"
ln -sf "$NEW/claude/local.claude-transcript-prune.plist" "$TRANSCRIPT_PLIST"
launchctl unload "$TRANSCRIPT_PLIST" 2>/dev/null || true
launchctl load -w "$TRANSCRIPT_PLIST"

PLAN_PLIST="$HOME/Library/LaunchAgents/local.claude-plan-prune.plist"
rm -f "$PLAN_PLIST"
sed "s|DOTFILES_DIR_PLACEHOLDER|$NEW|g" \
  "$NEW/claude/local.claude-plan-prune.plist" > "$PLAN_PLIST"
launchctl unload "$PLAN_PLIST" 2>/dev/null || true
launchctl load -w "$PLAN_PLIST"
echo "  launchd: OK"

# Clean up empty ~/Documents/code if it exists
if [ -d "$HOME/Documents/code" ] && [ -z "$(ls -A "$HOME/Documents/code")" ]; then
  rmdir "$HOME/Documents/code"
  echo "  removed empty ~/Documents/code"
fi

echo ""
echo "All done. Run 'source ~/.zshrc' to reload zsh."
