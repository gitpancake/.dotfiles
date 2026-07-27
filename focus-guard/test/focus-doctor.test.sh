#!/usr/bin/env bash
# Tests for focus-doctor.sh — sandboxed, no root/launchd/nginx.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCTOR="$HERE/../focus-doctor.sh"

pass=0; fail=0; fails=()
ok() { pass=$((pass+1)); printf '  \033[32mok\033[0m   %s\n' "$1"; }
no() { fail=$((fail+1)); fails+=("$1"); printf '  \033[31mFAIL\033[0m %s\n' "$1"; }
assert_rc()       { if [ "$2" = "$3" ]; then ok "$1"; else no "$1 (rc want $2 got $3)"; fi; }
assert_contains() { case "$2" in *"$3"*) ok "$1";; *) no "$1 (missing [$3])";; esac; }

new_sandbox() {
  SB="$(mktemp -d)"
  mkdir -p "$SB/state/certs"
  cat > "$SB/hosts.blocked" <<'EOF'
127.0.0.1       localhost
255.255.255.255 broadcasthost
::1             localhost
127.0.0.1	youtube.com
EOF
  awk '/^[[:space:]]*127\.0\.0\.1[[:space:]]+/{if($2=="localhost"){print;next}print "#"$0;next}{print}' \
    "$SB/hosts.blocked" > "$SB/hosts.open"
  cp "$SB/hosts.open" "$SB/hosts.live"
  echo "open" > "$SB/state/state"
  # Stubs: launchctl reports loaded, curl returns the sentinel.
  cat > "$SB/launchctl" <<'EOF'
#!/bin/bash
echo "system/$2 = { state = running }"
EOF
  cat > "$SB/curl" <<'EOF'
#!/bin/bash
printf 'FOCUS_GUARD_SENTINEL'
EOF
  chmod +x "$SB/launchctl" "$SB/curl"
  # Valid self-signed cert (30d).
  openssl req -x509 -newkey rsa:2048 -nodes -keyout "$SB/state/certs/key.pem" \
    -out "$SB/state/certs/cert.pem" -days 30 -subj /CN=focus-test >/dev/null 2>&1
  export FG_HOSTS_LIVE="$SB/hosts.live" FG_HOSTS_BLOCKED="$SB/hosts.blocked"
  export FG_HOSTS_OPEN="$SB/hosts.open" FG_STATE_DIR="$SB/state"
  export FG_FORCE_FOCUS=0
  export FG_DOCTOR_LAUNCHCTL="$SB/launchctl" FG_DOCTOR_CURL="$SB/curl"
  export FG_DOCTOR_PROBE_URL="http://stub" FG_DOCTOR_CERT="$SB/state/certs/cert.pem"
  export FG_DOCTOR_DAEMON_DIR="$SB"   # never read the real /Library/LaunchDaemons
  unset FG_DOCTOR_CERT_MIN_SECS 2>/dev/null || true
}
cleanup() { [ -n "${SB:-}" ] && rm -rf "$SB"; }
trap cleanup EXIT

echo "focus-doctor.sh tests"

# --- all healthy ---------------------------------------------------------
new_sandbox
out="$(bash "$DOCTOR" 2>&1)"; rc=$?
assert_rc       "healthy: rc 0"                 0 "$rc"
assert_contains "healthy: hosts consistent"     "$out" "↔ state consistent (open)"
assert_contains "healthy: nginx ok"             "$out" "nginx serving status page"
assert_contains "healthy: cert ok"              "$out" "TLS cert valid"
assert_contains "healthy: daemons loaded"       "$out" "local.focus-guard loaded"

# --- hosts/state desync (the original incident) --------------------------
new_sandbox
cp "$SB/hosts.blocked" "$SB/hosts.live"   # live=blocked, state=open
out="$(bash "$DOCTOR" 2>&1)"; rc=$?
assert_rc       "desync: rc 1"                  1 "$rc"
assert_contains "desync: flagged"               "$out" "but /etc/hosts is 'blocked'"

# --- daemon not loaded ---------------------------------------------------
new_sandbox
cat > "$SB/launchctl" <<'EOF'
#!/bin/bash
echo "Could not find service" >&2; exit 1
EOF
chmod +x "$SB/launchctl"
out="$(bash "$DOCTOR" 2>&1)"; rc=$?
assert_rc       "unloaded: rc 1"                1 "$rc"
assert_contains "unloaded: bootstrap hint"      "$out" "NOT loaded"

# --- nginx down ----------------------------------------------------------
new_sandbox
cat > "$SB/curl" <<'EOF'
#!/bin/bash
exit 7
EOF
chmod +x "$SB/curl"
out="$(bash "$DOCTOR" 2>&1)"; rc=$?
assert_rc       "nginx down: rc 1"              1 "$rc"
assert_contains "nginx down: flagged"           "$out" "nginx not answering probe"

# --- cert past validity window -------------------------------------------
# 1-day cert + a 200000s (~2.3d) requirement → checkend fails (proves the
# expiry gate; portable across openssl/LibreSSL where -days -1 is unreliable).
new_sandbox
openssl req -x509 -newkey rsa:2048 -nodes -keyout "$SB/state/certs/key.pem" \
  -out "$SB/state/certs/cert.pem" -days 1 -subj /CN=expiring >/dev/null 2>&1
export FG_DOCTOR_CERT_MIN_SECS=200000
out="$(bash "$DOCTOR" 2>&1)"; rc=$?
assert_rc       "expired cert: rc 1"            1 "$rc"
assert_contains "expired cert: flagged"         "$out" "TLS cert expired/invalid"

echo
echo "  $pass passed, $fail failed"
if [ "$fail" -gt 0 ]; then printf '  failed: %s\n' "${fails[@]}"; exit 1; fi
