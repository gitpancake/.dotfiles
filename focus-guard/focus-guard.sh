#!/bin/bash
# focus-guard — time-aware /etc/hosts blocker.
#
# Runs as root via a LaunchDaemon every 10 min (the `tick` path), plus
# `block` / `unblock` manual subcommands. Every tick enforces the intended
# /etc/hosts unconditionally (self-heal), verifies the copy actually landed,
# and derives the served status page from the *real* /etc/hosts — never from
# an assumed target. On a swap failure it serves a distinct "degraded" page
# and exits non-zero so launchd surfaces it.
#
# Paths are env-overridable (FG_*) purely so the test harness can sandbox it;
# in production every default points at the real system path.
set -euo pipefail

HOSTS_LIVE="${FG_HOSTS_LIVE:-/etc/hosts}"
HOSTS_BLOCKED="${FG_HOSTS_BLOCKED:-/etc/hosts.blocked}"
HOSTS_OPEN="${FG_HOSTS_OPEN:-/etc/hosts.open}"
STATE_DIR="${FG_STATE_DIR:-/usr/local/var/focus}"
STATE_FILE="$STATE_DIR/state"
STATUS_HTML="$STATE_DIR/index.html"
OVERRIDE_FILE="$STATE_DIR/override"

# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------

is_focus_time() {
  # Test seam: FG_FORCE_FOCUS=1 → always focus, =0 → never.
  if [ -n "${FG_FORCE_FOCUS:-}" ]; then
    [ "$FG_FORCE_FOCUS" = "1" ]
    return
  fi
  local day hour
  day=$(date +%u)    # 1=Mon … 7=Sun
  hour=$(date +%-H)  # 0-23, no leading zero
  if [ "$day" -le 5 ]; then
    [ "$hour" -ge 9 ] && [ "$hour" -lt 18 ]
  else
    [ "$hour" -ge 11 ] && [ "$hour" -lt 15 ]
  fi
}

next_change() {
  local day hour
  day=$(date +%u)
  hour=$(date +%-H)
  if [ "$day" -le 5 ]; then
    if [ "$hour" -lt 9 ];  then echo "09:00"; return; fi
    if [ "$hour" -lt 18 ]; then echo "18:00"; return; fi
    echo "09:00 tomorrow"
  else
    if [ "$hour" -lt 11 ]; then echo "11:00"; return; fi
    if [ "$hour" -lt 15 ]; then echo "15:00"; return; fi
    echo "09:00 Monday"
  fi
}

# ---------------------------------------------------------------------------
# Hosts state
# ---------------------------------------------------------------------------

# The "open" hosts file is *derived* from the blocked one: every active
# 127.0.0.1 block line is commented out, localhost/broadcasthost kept live.
# Deriving (vs a hand-maintained second file) makes open and blocked
# structurally impossible to desync — the root of the original incident.
derive_open_from_blocked() {
  awk '
    /^[[:space:]]*127\.0\.0\.1[[:space:]]+/ {
      if ($2 == "localhost") { print; next }
      print "#" $0; next
    }
    { print }
  ' "$HOSTS_BLOCKED"
}

flush_dns() {
  [ -n "${FG_SKIP_DNS_FLUSH:-}" ] && return 0
  command -v dscacheutil >/dev/null 2>&1 && dscacheutil -flushcache || true
  killall -HUP mDNSResponder 2>/dev/null || true
}

# Atomic replace: write into a temp file in the *same directory* as the
# destination (so mv is a rename, not a cross-device copy) then mv over.
# Replaces the original bare `cp` which could leave /etc/hosts half-written.
atomic_install() { # src dst
  local src=$1 dst=$2 tmp
  tmp=$(mktemp "${dst}.fg.XXXXXX")
  cat "$src" > "$tmp"
  chmod 0644 "$tmp"
  mv -f "$tmp" "$dst"
}

# Real state, by content comparison — not by trusting STATE_FILE.
actual_state() { # open_file
  local open_file=$1
  if cmp -s "$HOSTS_LIVE" "$HOSTS_BLOCKED"; then echo "blocked"; return; fi
  if cmp -s "$HOSTS_LIVE" "$open_file";    then echo "open";    return; fi
  echo "unknown"
}

# ---------------------------------------------------------------------------
# Status page
# ---------------------------------------------------------------------------

write_html() { # mode next   (mode: blocked|open|degraded)
  local mode=$1 next=$2 updated icon title subtitle detail probe_script=""
  updated=$(date "+%H:%M")

  if [ "$mode" = "blocked" ]; then
    icon="🔒"; title="Focus Mode"; subtitle="Back to work."
    detail="Unblocks at $next"
  elif [ "$mode" = "degraded" ]; then
    icon="⚠️"; title="focus-guard can't write /etc/hosts"
    subtitle="Enforcement is degraded."
    detail="The schedule daemon failed to swap /etc/hosts. Check: sudo launchctl print system/local.focus-guard — run focus-doctor.sh."
  else
    icon="🟢"; title="Unblocked"; subtitle="Checking DNS…"
    detail="Focus resumes at $next"
    # Browser-cache escape. /etc/hosts is open, but Chromium can keep a stale
    # 127.0.0.1 host-cache entry + pooled keep-alive socket pointing at nginx.
    # We probe a same-origin sentinel: if nginx still answers it, DNS is still
    # cached. One hard navigation is attempted first (busts some caches); after
    # K consecutive sentinel hits we STOP silently re-trapping and show
    # actionable copy instead of looping "Checking DNS…" forever.
    probe_script='<script>(function(){
  var SENT="FOCUS_GUARD_SENTINEL",K=4,hits=0,done=false;
  var u=new URL(location.href);
  if(!u.searchParams.has("_fg")){u.searchParams.set("_fg",Date.now());location.replace(u.toString());return;}
  function escape(){if(done)return;done=true;location.href=location.origin+"/?_fgx="+Date.now();}
  function stuck(){
    done=true;
    var c=document.querySelector(".card");
    if(!c)return;
    c.innerHTML="<div class=\"icon\">🌀</div><h1>DNS still cached</h1>"+
      "<p class=\"subtitle\">/etc/hosts is open, but your browser cached the block.</p>"+
      "<p class=\"detail\">Visit <b>chrome://net-internals/#dns</b> → Clear host cache, or fully quit &amp; reopen the browser. Then retry.</p>"+
      "<p style=\"margin-top:1.4rem\"><button onclick=\"location.href=location.origin+chr()\" "+
      "style=\"font:inherit;padding:.6rem 1.4rem;border:0;border-radius:8px;background:#0071e3;color:#fff;cursor:pointer\">Try again</button></p>";
    window.chr=function(){return "/?_fgx="+Date.now();};
  }
  function probe(){
    if(done)return;
    fetch("/__focus_guard_probe__?cb="+Date.now(),{cache:"no-store"})
      .then(function(r){return r.text();})
      .then(function(b){
        if(b!==SENT){escape();return;}
        hits++;
        if(hits>=K){stuck();}else{setTimeout(probe,3000);}
      })
      .catch(function(){escape();});
  }
  probe();
})();</script>'
  fi

  cat > "$STATUS_HTML" <<HTML
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="Cache-Control" content="no-store, no-cache, must-revalidate">
  <title>$title</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, sans-serif;
      background: #f5f5f7;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
    }
    .card {
      background: white;
      border-radius: 16px;
      padding: 2.5rem 3rem;
      text-align: center;
      box-shadow: 0 4px 24px rgba(0,0,0,0.08);
      max-width: 380px;
      width: 90%;
    }
    .icon     { font-size: 3.5rem; margin-bottom: 1rem; }
    h1        { font-size: 1.6rem; font-weight: 600; margin-bottom: 0.4rem; }
    .subtitle { color: #555; font-size: 1rem; margin-bottom: 1.2rem; }
    .detail   { color: #888; font-size: 0.85rem; }
    .updated  { color: #bbb; font-size: 0.75rem; margin-top: 1.5rem; }
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">$icon</div>
    <h1>$title</h1>
    <p class="subtitle">$subtitle</p>
    <p class="detail">$detail</p>
    <p class="updated">Updated $updated</p>
  </div>
  $probe_script
</body>
</html>
HTML
}

# ---------------------------------------------------------------------------
# Tick — the enforced, self-healing, verify-or-degrade core
# ---------------------------------------------------------------------------

tick() {
  local target current open_tmp intended next
  next=$(next_change)

  if [ -f "$OVERRIDE_FILE" ]; then
    target=$(cat "$OVERRIDE_FILE")
  elif is_focus_time; then
    target="blocked"
  else
    target="open"
  fi

  # Materialise the derived open file (also refresh /etc/hosts.open so other
  # tools / switch-hosts legacy callers see a correct, in-sync copy).
  open_tmp=$(mktemp "${STATE_DIR}/open.XXXXXX")
  derive_open_from_blocked > "$open_tmp"
  atomic_install "$open_tmp" "$HOSTS_OPEN" 2>/dev/null || cp "$open_tmp" "$HOSTS_OPEN" 2>/dev/null || true

  if [ "$target" = "blocked" ]; then
    intended="$HOSTS_BLOCKED"
  else
    intended="$open_tmp"
  fi

  # Always enforce — self-heal any drift every tick. Only the log line is
  # gated on change, never the swap.
  local applied=0 attempt
  for attempt in 1 2; do
    if [ -z "${FG_FORCE_MISMATCH:-}" ]; then
      atomic_install "$intended" "$HOSTS_LIVE"
    fi
    flush_dns
    if [ -z "${FG_FORCE_MISMATCH:-}" ] && cmp -s "$HOSTS_LIVE" "$intended"; then
      applied=1
      break
    fi
  done

  if [ "$applied" -ne 1 ]; then
    rm -f "$open_tmp"
    write_html degraded "$next"
    echo "$(date): DEGRADED — could not write $HOSTS_LIVE (target=$target)" >&2
    return 1
  fi

  current=$(cat "$STATE_FILE" 2>/dev/null || echo "unknown")
  if [ "$current" != "$target" ]; then
    echo "$target" > "$STATE_FILE"
    echo "$(date): switched to $target"
  fi

  # Page is derived from REAL /etc/hosts, not the assumed target.
  local real
  real=$(actual_state "$open_tmp")
  rm -f "$open_tmp"
  case "$real" in
    blocked) write_html blocked "$next" ;;
    open)    write_html open    "$next" ;;
    *)       write_html degraded "$next"
             echo "$(date): DEGRADED — $HOSTS_LIVE matches neither blocked nor open" >&2
             return 1 ;;
  esac
}

cmd_block() {
  mkdir -p "$STATE_DIR"
  echo "blocked" > "$OVERRIDE_FILE"
  tick
}

cmd_unblock() {
  rm -f "$OVERRIDE_FILE"
  tick
}

main() {
  case "${1:-tick}" in
    tick)    tick ;;
    block)   cmd_block ;;
    unblock) cmd_unblock ;;
    *) echo "usage: focus-guard.sh [tick|block|unblock]" >&2; exit 2 ;;
  esac
}

# Source-safe: tests source this file for unit access to the pure functions
# without triggering a tick.
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
  main "$@"
fi
