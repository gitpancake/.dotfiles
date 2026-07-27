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

# Focus Guard — scripts live in /usr/local/bin (root-owned, not symlinked),
# daemons in /Library/LaunchDaemons. Re-copy + re-bootstrap so edits in the
# repo actually take effect. Needs sudo; skip cleanly if unavailable.
if [ -d "$DOTFILES_DIR/focus-guard" ] && command -v sudo &>/dev/null \
   && sudo -n true 2>/dev/null; then
  for f in focus-guard.sh focus-doctor.sh cert-gen.sh block unblock; do
    sudo cp "$DOTFILES_DIR/focus-guard/$f" "/usr/local/bin/$f"
    sudo chmod +x "/usr/local/bin/$f"
  done
  sudo cp "$DOTFILES_DIR/focus-guard/focus.conf" /opt/homebrew/etc/nginx/focus.conf
  for plist in local.focus-guard.plist local.focus-nginx.plist; do
    label="${plist%.plist}"
    sudo cp "$DOTFILES_DIR/focus-guard/$plist" "/Library/LaunchDaemons/$plist"
    sudo chown root:wheel "/Library/LaunchDaemons/$plist"
    sudo chmod 644 "/Library/LaunchDaemons/$plist"
    sudo launchctl bootout "system/$label" 2>/dev/null || true
    sudo launchctl bootstrap system "/Library/LaunchDaemons/$plist"
    sudo launchctl enable "system/$label"
  done
  sudo /opt/homebrew/bin/nginx -s reload 2>/dev/null || true
  echo "  focus-guard: refreshed + daemons re-bootstrapped"
else
  echo "  focus-guard: skipped (needs passwordless sudo — run install-mac.sh"
  echo "    or: sudo rewire-symlinks.sh, to refresh /usr/local/bin + daemons)"
fi

# Clean up empty ~/Documents/code if it exists
if [ -d "$HOME/Documents/code" ] && [ -z "$(ls -A "$HOME/Documents/code")" ]; then
  rmdir "$HOME/Documents/code"
  echo "  removed empty ~/Documents/code"
fi

echo ""
echo "All done. Run 'source ~/.zshrc' to reload zsh."
