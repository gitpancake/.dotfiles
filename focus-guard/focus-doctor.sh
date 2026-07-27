#!/bin/bash
# focus-doctor — health check for focus-guard. Surfaces the silent failures
# the original incident hid: daemons not loaded, nginx unmanaged, /etc/hosts
# desynced from state, expired cert. Prints ✓/✗ lines; exits non-zero if any
# check FAILs so it can feed tmux/statusline or a launchd alarm.
#
# Usable as: focus-doctor.sh   (run with sudo for daemon-domain status).
# Paths/commands are FG_*-overridable for the test harness.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Shared pure functions (derive_open_from_blocked, actual_state, schedule).
# focus-guard.sh sets -e; doctor wants soft failures (collect all ✗), so
# restore -uo pipefail without -e after sourcing.
source "$HERE/focus-guard.sh"
set +e

LAUNCHCTL="${FG_DOCTOR_LAUNCHCTL:-launchctl}"
CURL="${FG_DOCTOR_CURL:-curl}"
PROBE_URL="${FG_DOCTOR_PROBE_URL:-http://127.0.0.1/__focus_guard_probe__}"
CERT="${FG_DOCTOR_CERT:-$STATE_DIR/certs/cert.pem}"
DAEMON_DIR="${FG_DOCTOR_DAEMON_DIR:-/Library/LaunchDaemons}"
# Seconds of validity required; 0 = "must not be already expired". Raise to
# warn ahead of expiry.
CERT_MIN_SECS="${FG_DOCTOR_CERT_MIN_SECS:-0}"

rc=0
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$1"; rc=1; }
note() { printf '  \033[33m•\033[0m %s\n' "$1"; }

check_daemons() {
  local label out st
  for label in local.focus-guard local.focus-nginx; do
    # Capture into a var (no pipe in the condition — pipefail would otherwise
    # surface launchctl's non-zero exit even when grep matched).
    out=$("$LAUNCHCTL" print "system/$label" 2>&1)
    st=$?
    if [ "$st" -eq 0 ]; then
      ok "$label loaded"
    else
      case "$out" in
        *[Cc]ould\ not\ find*)
          bad "$label NOT loaded (sudo launchctl bootstrap system $DAEMON_DIR/$label.plist)" ;;
        *)
          # Permission denied querying the system domain → can't tell. Fall
          # back to plist presence; tell the user to re-run with sudo.
          if [ -f "$DAEMON_DIR/$label.plist" ]; then
            note "$label plist present; run focus-doctor.sh with sudo for load status"
          else
            bad "$label.plist missing from $DAEMON_DIR"
          fi ;;
      esac
    fi
  done
}

check_nginx() {
  local body
  body=$("$CURL" -s --max-time 3 "$PROBE_URL" 2>/dev/null || true)
  if [ "$body" = "FOCUS_GUARD_SENTINEL" ]; then
    ok "nginx serving status page"
  else
    bad "nginx not answering probe ($PROBE_URL)"
  fi
}

check_hosts_state() {
  if [ ! -f "$HOSTS_BLOCKED" ]; then
    bad "$HOSTS_BLOCKED missing"
    return
  fi
  local open_tmp real state expected
  open_tmp=$(mktemp)
  derive_open_from_blocked > "$open_tmp"
  real=$(actual_state "$open_tmp")
  rm -f "$open_tmp"
  state=$(cat "$STATE_FILE" 2>/dev/null || echo "unknown")

  if [ "$real" = "unknown" ]; then
    bad "/etc/hosts matches neither blocked nor open (degraded)"
  elif [ "$real" != "$state" ]; then
    bad "state file says '$state' but /etc/hosts is '$real'"
  else
    ok "/etc/hosts ↔ state consistent ($real)"
  fi

  if [ -f "$OVERRIDE_FILE" ]; then
    expected=$(cat "$OVERRIDE_FILE")
  elif is_focus_time; then
    expected="blocked"
  else
    expected="open"
  fi
  if [ "$real" = "$expected" ]; then
    ok "/etc/hosts matches schedule (expected $expected)"
  else
    bad "/etc/hosts is '$real' but schedule/override expects '$expected'"
  fi
}

check_cert() {
  if [ ! -f "$CERT" ]; then
    bad "cert missing ($CERT)"
    return
  fi
  if openssl x509 -checkend "$CERT_MIN_SECS" -noout -in "$CERT" >/dev/null 2>&1; then
    ok "TLS cert valid"
  else
    bad "TLS cert expired/invalid ($CERT)"
  fi
}

main() {
  echo "focus-doctor"
  check_daemons
  check_nginx
  check_hosts_state
  check_cert
  echo
  if [ "$rc" -eq 0 ]; then echo "  all checks passed"; else echo "  FAILURES — focus-guard is degraded"; fi
  exit "$rc"
}

if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
  main "$@"
fi
