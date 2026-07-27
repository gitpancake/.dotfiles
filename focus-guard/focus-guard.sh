#!/bin/bash
set -euo pipefail

HOSTS_BLOCKED=/etc/hosts.blocked
HOSTS_OPEN=/etc/hosts.open
STATE_FILE=/usr/local/var/focus/state
STATUS_HTML=/usr/local/var/focus/index.html

is_focus_time() {
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

write_html() {
  local state=$1 next=$2 updated
  updated=$(date "+%H:%M")

  if [ "$state" = "blocked" ]; then
    local icon="🔒" title="Focus Mode" subtitle="Back to work." detail="Unblocks at $next"
  else
    local icon="🟢" title="Unblocked" subtitle="Enjoy your break." detail="Focus resumes at $next"
  fi

  cat > "$STATUS_HTML" <<HTML
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
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
</body>
</html>
HTML
}

main() {
  local target current

  if is_focus_time; then
    target="blocked"
  else
    target="open"
  fi

  current=$(cat "$STATE_FILE" 2>/dev/null || echo "unknown")

  if [ "$current" != "$target" ]; then
    if [ "$target" = "blocked" ]; then
      cp "$HOSTS_BLOCKED" /etc/hosts
    else
      cp "$HOSTS_OPEN" /etc/hosts
    fi
    dscacheutil -flushcache
    echo "$target" > "$STATE_FILE"
    echo "$(date): switched to $target"
  fi

  write_html "$target" "$(next_change)"
}

main
