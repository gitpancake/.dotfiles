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

# Daily pacing: 7-day limit / 7 = ~14.29% per day. Shows what fraction of today's
# allotment has been burned, derived from delta of 7d_pct since first sample today.
# State stored in ~/.claude/cache/daily-usage.json: {date, startPct}.
dailyUsedPctOfQuota() {
  local currentRaw=$1
  local stateDir=$HOME/.claude/cache
  local stateFile=$stateDir/daily-usage.json
  mkdir -p "$stateDir" 2>/dev/null
  local today; today=$(date +%Y-%m-%d)

  local storedDate="" storedPct=""
  if [[ -r "$stateFile" ]]; then
    read -r storedDate storedPct < <(
      jq -r '"\(.date // "") \(.startPct // 0)"' "$stateFile" 2>/dev/null
    )
  fi

  local needWrite=0
  if [[ "$storedDate" != "$today" ]]; then
    storedPct=$currentRaw
    needWrite=1
  elif awk -v c="$currentRaw" -v s="$storedPct" 'BEGIN{exit !(c+0 < s+0)}'; then
    # 7d window rolled (current < stored) → restart day baseline.
    storedPct=$currentRaw
    needWrite=1
  fi

  if (( needWrite )); then
    local tmp
    tmp=$(mktemp "$stateDir/.daily-usage.XXXXXX" 2>/dev/null) || tmp=""
    if [[ -n "$tmp" ]]; then
      printf '{"date":"%s","startPct":%s}\n' "$today" "$storedPct" > "$tmp"
      mv -f "$tmp" "$stateFile" 2>/dev/null || rm -f "$tmp"
    fi
  fi

  awk -v c="$currentRaw" -v s="$storedPct" 'BEGIN{
    d = c - s; if (d < 0) d = 0;
    q = 100 / 7;
    r = d / q * 100;
    if (r < 0) r = 0;
    if (r > 999) r = 999;
    printf "%d", r
  }'
}

renderDailyBucket() {
  local pct=$1
  local color; color=$(colorForPercent "$pct")
  printf ' %s│%s %sdy %d%%%s' "$dim" "$reset" "$color" "$pct" "$reset"
}

# Guard: skip rendering if values look like uninitialized garbage (timestamps, tiny sizes)
isValidPct() { [[ "$1" =~ ^[0-9]+$ ]] && (( $1 >= 0 && $1 <= 100 )); }
isValidSize() { [[ "$1" =~ ^[0-9]+$ ]] && (( $1 > 1000 )); }

if isValidPct "$ctxPct" && isValidSize "$ctxSize"; then
  renderContextBar
  if isValidPct "$sevenDayPct"; then
    renderDailyBucket "$(dailyUsedPctOfQuota "$sevenDayPctRaw")"
  fi
  isValidPct "$fiveHrPct"   && renderUsageBucket "5h" "$fiveHrPct"   "$fiveHrReset"
  isValidPct "$sevenDayPct" && renderUsageBucket "7d" "$sevenDayPct" "$sevenDayReset"
else
  printf '…'
fi
