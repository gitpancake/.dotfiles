#!/usr/bin/env bash
# Claude Code status line: context-window usage bar + usage-limit buckets.
# Reads the JSON blob Claude Code pipes on stdin and prints a single line.
#
# Context bar always shown. 5-hour and 7-day usage buckets appear only once
# either crosses usageThreshold, color-coded by severity, with a reset timer.

set -u

usageThreshold=50
barWidth=20

input=$(cat)

read -r ctxPct ctxSize fiveHrPct fiveHrReset sevenDayPct sevenDayReset sevenDayPctRaw < <(
  jq -r '
    [
      (.context_window.used_percentage         // 0 | floor),
      (.context_window.context_window_size     // 0),
      (.rate_limits.five_hour.used_percentage  // 0 | floor),
      (.rate_limits.five_hour.resets_at        // 0),
      (.rate_limits.seven_day.used_percentage  // 0 | floor),
      (.rate_limits.seven_day.resets_at        // 0),
      (.rate_limits.seven_day.used_percentage  // 0)
    ] | @tsv
  ' <<<"$input"
)

reset=$'\033[0m'
dim=$'\033[2m'

colorForPercent() {
  local p=$1
  if   (( p >= 91 )); then printf '\033[31m'
  elif (( p >= 76 )); then printf '\033[38;5;208m'
  elif (( p >= 51 )); then printf '\033[33m'
  else                     printf '\033[32m'
  fi
}

humanTokens() {
  local n=$1
  if (( n >= 1000000 )); then
    awk -v n="$n" 'BEGIN{printf (n%1000000==0 ? "%dM" : "%.1fM"), n/1000000}'
  elif (( n >= 1000 )); then
    awk -v n="$n" 'BEGIN{printf "%.1fk", n/1000}'
  else
    printf '%d' "$n"
  fi
}

humanDuration() {
  local secs=$1
  if   (( secs <= 0 ));     then printf '<1m'
  elif (( secs >= 86400 )); then printf '%dd %dh' $((secs/86400)) $(((secs%86400)/3600))
  elif (( secs >= 3600 )); then printf '%dh %dm' $((secs/3600)) $(((secs%3600)/60))
  elif (( secs >= 60 ));   then printf '%dm' $((secs/60))
  else                          printf '<1m'
  fi
}

renderContextBar() {
  local usedTokens=$(( ctxPct * ctxSize / 100 ))
  local filled=$(( (ctxPct * barWidth + 50) / 100 ))
  (( filled > barWidth )) && filled=$barWidth
  (( filled < 0 ))        && filled=0
  local empty=$(( barWidth - filled ))
  local color; color=$(colorForPercent "$ctxPct")

  local bar=''
  bar+=$(printf '█%.0s' $(seq 1 "$filled" 2>/dev/null))
  bar+=$(printf '░%.0s' $(seq 1 "$empty"  2>/dev/null))

  printf '%s[%s]%s %s/%s %s%d%%%s' \
    "$color" "$bar" "$reset" \
    "$(humanTokens "$usedTokens")" "$(humanTokens "$ctxSize")" \
    "$dim" "$ctxPct" "$reset"
}

renderUsageBucket() {
  local label=$1 pct=$2 resetAt=$3
  (( pct < usageThreshold )) && return
  local color; color=$(colorForPercent "$pct")
  local now; now=$(date +%s)
  local remaining=$(( resetAt - now ))
  printf ' %s│%s %s%s %d%%%s %s%s%s' \
    "$dim" "$reset" \
    "$color" "$label" "$pct" "$reset" \
    "$dim" "$(humanDuration "$remaining")" "$reset"
}

# Pace ratio: actual 7d% / expected linear 7d% at this point in stint.
# 100% = on pace. >100% = burning faster than sustainable. <100% = behind pace.
# Stateless — pure function of current 7d% and reset timestamp.
paceRatio() {
  local pct=$1 resetAt=$2
  awk -v p="$pct" -v r="$resetAt" -v n="$(date +%s)" 'BEGIN{
    days = (r - n) / 86400;
    if (days < 0) days = 0;
    if (days > 7) days = 7;
    expected = (1 - days / 7) * 100;
    if (expected < 0.1) expected = 0.1;
    ratio = p / expected * 100;
    if (ratio < 0) ratio = 0;
    if (ratio > 999) ratio = 999;
    printf "%d", ratio
  }'
}

colorForPace() {
  local p=$1
  if   (( p >= 130 )); then printf '\033[31m'
  elif (( p >= 115 )); then printf '\033[38;5;208m'
  elif (( p >= 105 )); then printf '\033[33m'
  else                      printf '\033[32m'
  fi
}

renderPaceBucket() {
  local pct=$1
  local color; color=$(colorForPace "$pct")
  printf ' %s│%s %space %d%%%s' "$dim" "$reset" "$color" "$pct" "$reset"
}

# Guard: skip rendering if values look like uninitialized garbage (timestamps, tiny sizes)
isValidPct() { [[ "$1" =~ ^[0-9]+$ ]] && (( $1 >= 0 && $1 <= 100 )); }
isValidSize() { [[ "$1" =~ ^[0-9]+$ ]] && (( $1 > 1000 )); }

if isValidPct "$ctxPct" && isValidSize "$ctxSize"; then
  renderContextBar
  if isValidPct "$sevenDayPct"; then
    renderPaceBucket "$(paceRatio "$sevenDayPctRaw" "$sevenDayReset")"
  fi
  isValidPct "$fiveHrPct"   && renderUsageBucket "5h" "$fiveHrPct"   "$fiveHrReset"
  isValidPct "$sevenDayPct" && renderUsageBucket "7d" "$sevenDayPct" "$sevenDayReset"
else
  printf '…'
fi
