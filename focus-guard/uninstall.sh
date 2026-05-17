#!/usr/bin/env bash
# focus-guard uninstaller. Removes daemons, scripts, nginx config, runtime
# state. Leaves /etc/hosts in its "open" form (no 127.0.0.1 blocks).
#
# Does NOT uninstall brew formulae (mkcert/nss/nginx) — those may be in use
# elsewhere. Remove with `brew uninstall` manually if no longer needed.
set -euo pipefail

if ! command -v sudo &>/dev/null; then
  echo "focus-guard uninstall requires sudo" >&2
  exit 1
fi

# Stop + remove LaunchDaemons
for label in local.focus-guard local.focus-nginx; do
  sudo launchctl bootout "system/$label" 2>/dev/null || true
  sudo rm -f "/Library/LaunchDaemons/$label.plist"
done

# Scripts
for f in focus-guard.sh focus-doctor.sh cert-gen.sh block unblock; do
  sudo rm -f "/usr/local/bin/$f"
done

# nginx config — drop include line + remove the file
sudo rm -f /opt/homebrew/etc/nginx/focus.conf
if [ -f /opt/homebrew/etc/nginx/nginx.conf ]; then
  sudo sed -i '' '/include \/opt\/homebrew\/etc\/nginx\/focus\.conf;/d' \
    /opt/homebrew/etc/nginx/nginx.conf
  sudo /opt/homebrew/bin/nginx -s reload 2>/dev/null || true
fi

# Restore /etc/hosts to its "open" form (strip active 127.0.0.1 blocks that
# came from /etc/hosts.blocked). Keep localhost/broadcasthost.
if [ -f /etc/hosts ]; then
  sudo cp /etc/hosts /etc/hosts.bak.focus-uninstall
  # Strip any line whose first field is 127.0.0.1 mapping to a non-localhost host.
  sudo awk '
    /^[[:space:]]*#/ { print; next }
    $1 == "127.0.0.1" && $2 != "localhost" && $2 != "broadcasthost" { next }
    { print }
  ' /etc/hosts.bak.focus-uninstall | sudo tee /etc/hosts >/dev/null
  echo "  Restored /etc/hosts (backup: /etc/hosts.bak.focus-uninstall)"
fi

# Runtime state
sudo rm -f /etc/hosts.blocked /etc/hosts.open
sudo rm -rf /usr/local/var/focus

echo "  focus-guard uninstalled. Brew formulae (mkcert/nss/nginx) left in place."
