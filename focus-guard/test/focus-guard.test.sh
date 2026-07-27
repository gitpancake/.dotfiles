#!/usr/bin/env bash
# Self-contained test harness for focus-guard.sh — no root, no launchd, no nginx.
# Runs focus-guard.sh's pure logic against a per-test sandbox via FG_* env
# overrides. Run: bash focus-guard/test/focus-guard.test.sh
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$HERE/../focus-guard.sh"

pass=0
fail=0
fails=()

ok()   { pass=$((pass + 1)); printf '  \033[32mok\033[0m   %s\n' "$1"; }
no()   { fail=$((fail + 1)); fails+=("$1"); printf '  \033[31mFAIL\033[0m %s\n' "$1"; }

assert_eq() { # desc expected actual
  if [ "$2" = "$3" ]; then ok "$1"; else no "$1 (expected [$2], got [$3])"; fi
}
assert_contains() { # desc haystack needle
  case "$2" in *"$3"*) ok "$1" ;; *) no "$1 (missing [$3])" ;; esac
}
assert_not_contains() { # desc haystack needle
  case "$2" in *"$3"*) no "$1 (unexpected [$3])" ;; *) ok "$1" ;; esac
}
assert_rc() { # desc expected_rc actual_rc
  if [ "$2" = "$3" ]; then ok "$1"; else no "$1 (expected rc $2, got $3)"; fi
}

# Per-test sandbox. Sets FG_* so focus-guard.sh never touches the real system.
new_sandbox() {
  SB="$(mktemp -d)"
  mkdir -p "$SB/state"
  cat > "$SB/hosts.blocked" <<'EOF'
127.0.0.1       localhost
255.255.255.255 broadcasthost
::1             localhost
127.0.0.1	youtube.com
127.0.0.1	www.youtube.com
127.0.0.1	reddit.com
EOF
  printf '127.0.0.1       localhost\n255.255.255.255 broadcasthost\n::1             localhost\n' \
    > "$SB/hosts.live"
  export FG_HOSTS_LIVE="$SB/hosts.live"
  export FG_HOSTS_BLOCKED="$SB/hosts.blocked"
  export FG_HOSTS_OPEN="$SB/hosts.open"
  export FG_STATE_DIR="$SB/state"
  export FG_SKIP_DNS_FLUSH=1
  unset FG_FORCE_FOCUS FG_FORCE_MISMATCH FG_FORCE_BUSY 2>/dev/null || true
}
cleanup() { [ -n "${SB:-}" ] && rm -rf "$SB"; }
trap cleanup EXIT

run() { ( "$SCRIPT" "$@" ) ; }   # subshell: isolate set -e / exit

echo "focus-guard.sh tests"

# --- derive_open_from_blocked --------------------------------------------
new_sandbox
open_out="$(FG_FORCE_FOCUS=0 bash -c 'source "$0"; derive_open_from_blocked' "$SCRIPT")"
assert_contains   "derive: keeps localhost"            "$open_out" "127.0.0.1       localhost"
assert_contains   "derive: keeps broadcasthost"        "$open_out" "255.255.255.255 broadcasthost"
assert_contains   "derive: comments youtube"           "$open_out" "#127.0.0.1	youtube.com"
assert_not_contains "derive: no active youtube block"  "$open_out" $'\n127.0.0.1\tyoutube.com'

# --- tick: open target (outside focus, no override) ----------------------
new_sandbox
out="$(FG_FORCE_FOCUS=0 run)"; rc=$?
assert_rc        "tick open: rc 0"                 0 "$rc"
assert_eq        "tick open: state=open"           "open" "$(cat "$SB/state/state")"
assert_contains  "tick open: html Unblocked"       "$(cat "$SB/state/index.html")" "Unblocked"
assert_not_contains "tick open: live has no block" "$(cat "$SB/hosts.live")" $'\n127.0.0.1\tyoutube.com'
assert_contains  "tick open: refreshes hosts.open" "$(cat "$SB/hosts.open")" "#127.0.0.1	youtube.com"

# --- tick: blocked target (inside focus) ---------------------------------
new_sandbox
out="$(FG_FORCE_FOCUS=1 run)"; rc=$?
assert_rc        "tick blocked: rc 0"              0 "$rc"
assert_eq        "tick blocked: state=blocked"     "blocked" "$(cat "$SB/state/state")"
assert_contains  "tick blocked: html Focus"        "$(cat "$SB/state/index.html")" "Focus Mode"
assert_contains  "tick blocked: live blocks yt"    "$(cat "$SB/hosts.live")" $'127.0.0.1\tyoutube.com'

# --- self-heal: live drifted to blocked while target=open ----------------
new_sandbox
cp "$SB/hosts.blocked" "$SB/hosts.live"          # drift
echo "blocked" > "$SB/state/state"               # stale state
out="$(FG_FORCE_FOCUS=0 run)"; rc=$?
assert_rc        "self-heal: rc 0"                 0 "$rc"
assert_eq        "self-heal: state corrected"      "open" "$(cat "$SB/state/state")"
assert_not_contains "self-heal: block removed"     "$(cat "$SB/hosts.live")" $'\n127.0.0.1\tyoutube.com'
assert_contains  "self-heal: html Unblocked"       "$(cat "$SB/state/index.html")" "Unblocked"

# --- verify-or-degrade: copy lands wrong → degraded page + rc 1 ----------
new_sandbox
out="$(FG_FORCE_FOCUS=0 FG_FORCE_MISMATCH=1 run 2>/dev/null)"; rc=$?
assert_rc        "degrade: non-zero exit"          1 "$rc"
html="$(cat "$SB/state/index.html")"
assert_contains  "degrade: distinct page"          "$html" "can't write /etc/hosts"
assert_not_contains "degrade: NOT Unblocked"       "$html" "🟢"

# --- real-state-derived HTML: target=open but mismatch → not Unblocked ---
# (covered above: degrade path proves html derives from real cmp, not target)

# --- block subcommand: sets override + applies blocked -------------------
new_sandbox
out="$(FG_FORCE_FOCUS=0 run block)"; rc=$?
assert_rc        "block cmd: rc 0"                 0 "$rc"
assert_eq        "block cmd: override=blocked"     "blocked" "$(cat "$SB/state/override")"
assert_eq        "block cmd: state=blocked"        "blocked" "$(cat "$SB/state/state")"
assert_contains  "block cmd: live blocks yt"       "$(cat "$SB/hosts.live")" $'127.0.0.1\tyoutube.com'

# --- override beats schedule: override=blocked wins outside focus --------
new_sandbox
echo "blocked" > "$SB/state/override"
out="$(FG_FORCE_FOCUS=0 run)"; rc=$?
assert_eq        "override: stays blocked"         "blocked" "$(cat "$SB/state/state")"

# --- unblock subcommand: clears override + applies schedule -------------
new_sandbox
echo "blocked" > "$SB/state/override"
cp "$SB/hosts.blocked" "$SB/hosts.live"
out="$(FG_FORCE_FOCUS=0 run unblock)"; rc=$?
assert_rc        "unblock cmd: rc 0"               0 "$rc"
assert_eq        "unblock cmd: override gone"      "1" "$([ ! -f "$SB/state/override" ] && echo 1 || echo 0)"
assert_eq        "unblock cmd: state=open"         "open" "$(cat "$SB/state/state")"

# --- summary -------------------------------------------------------------
echo
echo "  $pass passed, $fail failed"
if [ "$fail" -gt 0 ]; then
  printf '  failed: %s\n' "${fails[@]}"
  exit 1
fi
