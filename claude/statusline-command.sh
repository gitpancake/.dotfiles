#!/usr/bin/env bash
# Claude Code status line: context-window usage bar + token count.
# Reads the JSON blob Claude Code pipes on stdin and prints a single line.

set -u

input=$(cat)

read -r percent size < <(
  jq -r '"\(.context_window.used_percentage) \(.context_window.context_window_size)"' <<<"$input"
)

usedTokens=$(( percent * size / 100 ))

# Humanize: 42600 -> 42.6k, 1000000 -> 1M, 999 -> 999.
humanize() {
  local n=$1
  if (( n >= 1000000 )); then
    awk -v n="$n" 'BEGIN{printf (n%1000000==0 ? "%dM" : "%.1fM"), n/1000000}'
  elif (( n >= 1000 )); then
    awk -v n="$n" 'BEGIN{printf "%.1fk", n/1000}'
  else
    printf '%d' "$n"
  fi
}

usedStr=$(humanize "$usedTokens")
sizeStr=$(humanize "$size")

# 20-cell bar; each cell = 5% of the window.
barWidth=20
filledCells=$(( (percent * barWidth + 50) / 100 ))
(( filledCells > barWidth )) && filledCells=$barWidth
(( filledCells < 0 ))        && filledCells=0
emptyCells=$(( barWidth - filledCells ))

# Threshold colors match tmux-status.sh: green / yellow / orange / red.
if   (( percent >= 91 )); then color=$'\033[31m'
elif (( percent >= 76 )); then color=$'\033[38;5;208m'
elif (( percent >= 51 )); then color=$'\033[33m'
else                            color=$'\033[32m'
fi
dim=$'\033[2m'
reset=$'\033[0m'

bar=$(printf '█%.0s' $(seq 1 "$filledCells" 2>/dev/null))
bar+=$(printf '░%.0s' $(seq 1 "$emptyCells" 2>/dev/null))

printf '%s[%s]%s %s/%s %s%d%%%s' \
  "$color" "$bar" "$reset" \
  "$usedStr" "$sizeStr" \
  "$dim" "$percent" "$reset"
