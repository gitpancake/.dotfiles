#!/usr/bin/env bash
# focus-guard installer. Standalone — not part of the main dotfiles install.
#
# Installs scripts to /usr/local/bin, wires nginx, bootstraps the two
# LaunchDaemons. Idempotent — safe to re-run as a refresh after editing the
# source files in this repo.
#
# Run: ./focus-guard/install.sh   (from repo root, or anywhere — resolves)
#
# Uninstall: ./focus-guard/uninstall.sh
set -euo pipefail

FG_DIR="$(cd "$(dirname "$0")" && pwd)"

if ! command -v sudo &>/dev/null; then
  echo "focus-guard install requires sudo" >&2
  exit 1
fi

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
  sudo cp "$FG_DIR/$f" "/usr/local/bin/$f"
  sudo chmod +x "/usr/local/bin/$f"
done

# nginx config
sudo cp "$FG_DIR/focus.conf" /opt/homebrew/etc/nginx/focus.conf
if ! grep -q "focus.conf" /opt/homebrew/etc/nginx/nginx.conf; then
  sudo sed -i '' 's|include servers/\*;|include servers/*;\n    include /opt/homebrew/etc/nginx/focus.conf;|' \
    /opt/homebrew/etc/nginx/nginx.conf
fi

# hosts.blocked — skip if already exists (contains private domain list)
if [ ! -f /etc/hosts.blocked ]; then
  sudo cp "$FG_DIR/hosts.blocked.example" /etc/hosts.blocked
  echo "  Created /etc/hosts.blocked from example — add your domains before running focus-guard"
fi

# Generate initial certs + state before starting daemons
sudo mkdir -p /opt/homebrew/var/run
sudo /usr/local/bin/cert-gen.sh
sudo /opt/homebrew/bin/nginx -t
sudo /usr/local/bin/focus-guard.sh

# LaunchDaemons (root — only root can write /etc/hosts on the 10-min tick;
# LaunchAgents run as the user and silently fail the swap). Use the modern
# bootstrap/bootout API.
for plist in local.focus-guard.plist local.focus-nginx.plist; do
  label="${plist%.plist}"
  sudo cp "$FG_DIR/$plist" "/Library/LaunchDaemons/$plist"
  sudo chown root:wheel "/Library/LaunchDaemons/$plist"
  sudo chmod 644 "/Library/LaunchDaemons/$plist"
  sudo launchctl bootout "system/$label" 2>/dev/null || true
  sudo launchctl bootstrap system "/Library/LaunchDaemons/$plist"
  sudo launchctl enable "system/$label"
done

sudo /opt/homebrew/bin/nginx -s reload 2>/dev/null || true

if sudo /usr/local/bin/focus-doctor.sh; then
  echo "  Focus Guard installed and healthy"
else
  echo "  Focus Guard installed — focus-doctor reported issues (see above)"
fi
