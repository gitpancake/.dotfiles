#!/usr/bin/env bash
# Rewires all dotfile symlinks to point to ~/.dotfiles
set -euo pipefail
DOTFILES_DIR="$HOME/.dotfiles"

source "$DOTFILES_DIR/_link-dotfiles.sh"
echo "  symlinks: OK"

# LaunchAgents
TRANSCRIPT_PLIST="$HOME/Library/LaunchAgents/local.claude-transcript-prune.plist"
rm -f "$TRANSCRIPT_PLIST"
sed "s|DOTFILES_DIR_PLACEHOLDER|$DOTFILES_DIR|g" \
  "$DOTFILES_DIR/claude/local.claude-transcript-prune.plist" > "$TRANSCRIPT_PLIST"
launchctl unload "$TRANSCRIPT_PLIST" 2>/dev/null || true
launchctl load -w "$TRANSCRIPT_PLIST"

PLAN_PLIST="$HOME/Library/LaunchAgents/local.claude-plan-prune.plist"
rm -f "$PLAN_PLIST"
sed "s|DOTFILES_DIR_PLACEHOLDER|$DOTFILES_DIR|g" \
  "$DOTFILES_DIR/claude/local.claude-plan-prune.plist" > "$PLAN_PLIST"
launchctl unload "$PLAN_PLIST" 2>/dev/null || true
launchctl load -w "$PLAN_PLIST"

WT_GC_PLIST="$HOME/Library/LaunchAgents/local.claude-wt-gc.plist"
rm -f "$WT_GC_PLIST"
sed "s|DOTFILES_DIR_PLACEHOLDER|$DOTFILES_DIR|g" \
  "$DOTFILES_DIR/claude/local.claude-wt-gc.plist" > "$WT_GC_PLIST"
launchctl unload "$WT_GC_PLIST" 2>/dev/null || true
launchctl load -w "$WT_GC_PLIST"

# slack-tldr daemon (only loads if config exists; placeholder substitution
# means we always regenerate rather than symlink).
SLACK_PLIST="$HOME/Library/LaunchAgents/local.slack-tldr.plist"
rm -f "$SLACK_PLIST"
sed "s|DOTFILES_DIR_PLACEHOLDER|$DOTFILES_DIR|g" \
  "$DOTFILES_DIR/claude/local.slack-tldr.plist" > "$SLACK_PLIST"
launchctl unload "$SLACK_PLIST" 2>/dev/null || true
if [ -f "$DOTFILES_DIR/scripts/slack-tldr.config.local" ]; then
  launchctl load -w "$SLACK_PLIST"
  echo "  slack-tldr: loaded"
else
  echo "  slack-tldr: skipped (no scripts/slack-tldr.config.local)"
fi
echo "  launchd: OK"

# focus-guard — only refresh if already installed at the system level.
# Standalone installer + uninstaller live at focus-guard/{install,uninstall}.sh.
if [ -f /Library/LaunchDaemons/local.focus-guard.plist ] && command -v sudo &>/dev/null \
   && sudo -n true 2>/dev/null; then
  "$DOTFILES_DIR/focus-guard/install.sh"
  echo "  focus-guard: refreshed"
else
  echo "  focus-guard: skipped (not installed, or sudo unavailable)"
fi

# Clean up empty ~/Documents/code if it exists
if [ -d "$HOME/Documents/code" ] && [ -z "$(ls -A "$HOME/Documents/code")" ]; then
  rmdir "$HOME/Documents/code"
  echo "  removed empty ~/Documents/code"
fi

echo ""
echo "All done. Run 'source ~/.zshrc' to reload zsh."
