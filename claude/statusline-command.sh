#!/usr/bin/env bash

# --- Battery ---
BAT_PATH="/sys/class/power_supply/BAT1/capacity"
AC_PATH="/sys/class/power_supply/AC1/online"
BAT=""
if [ -f "$BAT_PATH" ]; then
  BATTERY=$(cat "$BAT_PATH")
  if [ -f "$AC_PATH" ] && [ "$(cat "$AC_PATH")" = "1" ]; then
    BAT="🔋${BATTERY}%⚡"
  else
    BAT="🔋${BATTERY}%"
  fi
fi

# --- CPU (load average as % of cores) ---
CORES=$(nproc)
LOAD=$(awk '{print $1}' /proc/loadavg)
CPU_PCT=$(awk "BEGIN {printf \"%.0f\", ($LOAD / $CORES) * 100}")
CPU="CPU ${CPU_PCT}%"

# --- Memory ---
MEM_PCT=$(awk '/MemTotal/{t=$2} /MemAvailable/{a=$2} END{printf "%.0f", (1-a/t)*100}' /proc/meminfo)
MEM="MEM ${MEM_PCT}%"

# --- Disk ---
DSK_PCT=$(df / | awk 'NR==2{print $5}')
DSK="DSK ${DSK_PCT}"

# --- Git branch (truncate if long) ---
GIT=""
BRANCH=$(git branch --show-current 2>/dev/null)
if [ -n "$BRANCH" ]; then
  if [ ${#BRANCH} -gt 20 ]; then
    BRANCH="${BRANCH:0:17}..."
  fi
  GIT="⎇ ${BRANCH}"
fi

# --- Node version ---
NODE="⬢ $(node --version 2>/dev/null || echo 'n/a')"

# --- Session duration (per parent process) ---
SESSION_FILE="/tmp/.claude-statusline-start-${PPID}"
if [ ! -f "$SESSION_FILE" ]; then
  date +%s > "$SESSION_FILE"
fi
START=$(cat "$SESSION_FILE")
NOW=$(date +%s)
ELAPSED=$(( NOW - START ))
HOURS=$(( ELAPSED / 3600 ))
MINS=$(( (ELAPSED % 3600) / 60 ))
if [ "$HOURS" -gt 0 ]; then
  DUR="⏱ ${HOURS}h${MINS}m"
else
  DUR="⏱ ${MINS}m"
fi

# --- Time ---
TIME=$(date +%H:%M:%S)

# --- Assemble ---
SEP=" │ "
OUT=""
[ -n "$BAT" ] && OUT="${BAT}${SEP}"
OUT+="${CPU}${SEP}${MEM}${SEP}${DSK}"
[ -n "$GIT" ] && OUT+="${SEP}${GIT}"
OUT+="${SEP}${NODE}${SEP}${DUR}${SEP}${TIME}"

printf '%s' "$OUT"
