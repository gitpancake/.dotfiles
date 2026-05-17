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

for pkg in tmux zoxide fzf glow; do
  if ! command -v "$pkg" &>/dev/null; then
    echo "  Installing $pkg..."
    brew install "$pkg"
  else
    echo "  $pkg: already installed"
  fi
done

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
source "$DOTFILES_DIR/_link-dotfiles.sh"
echo "  Linked dotfiles"

# Alacritty (macOS only)
if ! brew list --cask alacritty &>/dev/null && [ ! -d /Applications/Alacritty.app ]; then
  echo "  Installing Alacritty..."
  brew install --cask alacritty
else
  echo "  Alacritty: already installed"
fi
mkdir -p ~/.config/alacritty
ln -sf "$DOTFILES_DIR/alacritty/alacritty.toml" ~/.config/alacritty/alacritty.toml
ln -sfn "$DOTFILES_DIR/alacritty/themes" ~/.config/alacritty/themes
echo "  Linked Alacritty config"

# Claude auto-prune launchd jobs
mkdir -p ~/Library/LaunchAgents ~/.claude/logs

TRANSCRIPT_PLIST="$HOME/Library/LaunchAgents/local.claude-transcript-prune.plist"
rm -f "$TRANSCRIPT_PLIST"
sed "s|DOTFILES_DIR_PLACEHOLDER|$DOTFILES_DIR|g" \
  "$DOTFILES_DIR/claude/local.claude-transcript-prune.plist" > "$TRANSCRIPT_PLIST"
launchctl unload "$TRANSCRIPT_PLIST" 2>/dev/null || true
launchctl load -w "$TRANSCRIPT_PLIST"

PLAN_PLIST="$HOME/Library/LaunchAgents/local.claude-plan-prune.plist"
# Generate (not symlink) — LaunchAgent execve() doesn't expand $HOME in ProgramArguments
rm -f "$PLAN_PLIST"
sed "s|DOTFILES_DIR_PLACEHOLDER|$DOTFILES_DIR|g" \
  "$DOTFILES_DIR/claude/local.claude-plan-prune.plist" > "$PLAN_PLIST"
launchctl unload "$PLAN_PLIST" 2>/dev/null || true
launchctl load -w "$PLAN_PLIST"

echo "  Loaded Claude transcript + plan auto-prune launchd jobs"

# slack-tldr — Slack alerts → Haiku TLDR pane
if ! python3 -c "import slack_sdk" &>/dev/null; then
  echo "  Installing slack_sdk (user pip)..."
  pip3 install --user --quiet slack_sdk
fi
SLACK_PLIST="$HOME/Library/LaunchAgents/local.slack-tldr.plist"
rm -f "$SLACK_PLIST"
sed "s|DOTFILES_DIR_PLACEHOLDER|$DOTFILES_DIR|g" \
  "$DOTFILES_DIR/claude/local.slack-tldr.plist" > "$SLACK_PLIST"
launchctl unload "$SLACK_PLIST" 2>/dev/null || true
if [ -f "$DOTFILES_DIR/scripts/slack-tldr.config.local" ]; then
  launchctl load -w "$SLACK_PLIST"
  echo "  slack-tldr daemon loaded"
else
  echo "  slack-tldr config missing — copy scripts/slack-tldr.config.example.json"
  echo "    → scripts/slack-tldr.config.local, fill tokens, then:"
  echo "      launchctl load -w $SLACK_PLIST"
fi

# Focus Guard (requires sudo for /usr/local/bin and /Library/LaunchDaemons)
if command -v sudo &>/dev/null; then
  # Dependencies
  for pkg in mkcert nss nginx; do
    if ! brew list "$pkg" &>/dev/null; then
      echo "  Installing $pkg..."
      brew install "$pkg"
    fi
  done
  mkcert -install

  # Runtime dirs
  sudo mkdir -p /usr/local/bin /usr/local/var/focus/certs /usr/local/var/log

  # Scripts + commands
  for f in focus-guard.sh focus-doctor.sh cert-gen.sh block unblock; do
    sudo cp "$DOTFILES_DIR/focus-guard/$f" "/usr/local/bin/$f"
    sudo chmod +x "/usr/local/bin/$f"
  done

  # nginx config
  sudo cp "$DOTFILES_DIR/focus-guard/focus.conf" /opt/homebrew/etc/nginx/focus.conf
  if ! grep -q "focus.conf" /opt/homebrew/etc/nginx/nginx.conf; then
    sudo sed -i '' 's|include servers/\*;|include servers/*;\n    include /opt/homebrew/etc/nginx/focus.conf;|' \
      /opt/homebrew/etc/nginx/nginx.conf
  fi

  # hosts.blocked — skip if already exists (contains private domain list)
  if [ ! -f /etc/hosts.blocked ]; then
    sudo cp "$DOTFILES_DIR/focus-guard/hosts.blocked.example" /etc/hosts.blocked
    echo "  Created /etc/hosts.blocked from example — add your domains before running focus-guard"
  fi

  # Generate initial certs + state before starting daemons
  sudo mkdir -p /opt/homebrew/var/run
  sudo /usr/local/bin/cert-gen.sh
  sudo /opt/homebrew/bin/nginx -t
  sudo /usr/local/bin/focus-guard.sh

  # LaunchDaemons (root — only root can write /etc/hosts on the 10-min tick;
  # LaunchAgents run as the user and silently fail the swap). Use the modern
  # bootstrap/bootout API: legacy `launchctl load` is a no-op for system
  # daemons on current macOS, which is why the scheduler was never running.
  for plist in local.focus-guard.plist local.focus-nginx.plist; do
    label="${plist%.plist}"
    sudo cp "$DOTFILES_DIR/focus-guard/$plist" "/Library/LaunchDaemons/$plist"
    sudo chown root:wheel "/Library/LaunchDaemons/$plist"
    sudo chmod 644 "/Library/LaunchDaemons/$plist"
    sudo launchctl bootout "system/$label" 2>/dev/null || true
    sudo launchctl bootstrap system "/Library/LaunchDaemons/$plist"
    sudo launchctl enable "system/$label"
  done

  if sudo /usr/local/bin/focus-doctor.sh; then
    echo "  Focus Guard installed and healthy"
  else
    echo "  Focus Guard installed — focus-doctor reported issues (see above)"
  fi
else
  echo "  Skipping Focus Guard (sudo not available)"
fi

echo ""
echo "Done! Run 'source ~/.zshrc' to reload."
