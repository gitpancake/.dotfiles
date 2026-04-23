#!/bin/bash
set -euo pipefail

HOSTS_BLOCKED=/etc/hosts.blocked
CERT_DIR=/usr/local/var/focus/certs
DOMAINS_FILE=/usr/local/var/focus/domains.txt
MKCERT=/opt/homebrew/bin/mkcert

get_domains() {
  grep -E "^127\.0\.0\.1" "$HOSTS_BLOCKED" \
    | awk '{print $2}' \
    | grep -v -E "^(localhost|broadcasthost)$" \
    | sort -u
}

main() {
  mkdir -p "$CERT_DIR"

  local domains
  domains=$(get_domains)

  local prev_domains
  prev_domains=$(cat "$DOMAINS_FILE" 2>/dev/null || echo "")

  if [ "$domains" = "$prev_domains" ] && [ -f "$CERT_DIR/cert.pem" ]; then
    echo "Domains unchanged, skipping cert regeneration"
    exit 0
  fi

  echo "Regenerating cert for $(echo "$domains" | wc -l | tr -d ' ') domains"

  local caroot
  caroot=$(sudo -u "$SUDO_USER" "$MKCERT" -CAROOT)

  local domain_args=()
  while IFS= read -r d; do
    domain_args+=("$d")
  done <<< "$domains"

  local tmpdir
  tmpdir=$(sudo -u "$SUDO_USER" mktemp -d)
  pushd "$tmpdir" > /dev/null
  CAROOT="$caroot" sudo -u "$SUDO_USER" "$MKCERT" \
    -cert-file cert.pem \
    -key-file key.pem \
    "${domain_args[@]}"
  popd > /dev/null
  mv "$tmpdir/cert.pem" "$CERT_DIR/cert.pem"
  mv "$tmpdir/key.pem"  "$CERT_DIR/key.pem"
  rmdir "$tmpdir"

  echo "$domains" > "$DOMAINS_FILE"
  echo "Done. Run: sudo /opt/homebrew/bin/nginx -s reload"
}

main
