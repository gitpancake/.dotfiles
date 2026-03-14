#!/usr/bin/env bash

# Battery
BAT=""
BAT_PATH="/sys/class/power_supply/BAT1/capacity"
AC_PATH="/sys/class/power_supply/AC1/online"
if [ -f "$BAT_PATH" ]; then
  PCT=$(cat "$BAT_PATH")
  if [ -f "$AC_PATH" ] && [ "$(cat "$AC_PATH")" = "1" ]; then
    BAT="${PCT}%+"
  else
    BAT="${PCT}%"
  fi
fi

# CPU (load average as % of cores)
CORES=$(nproc)
LOAD=$(awk '{print $1}' /proc/loadavg)
CPU=$(awk "BEGIN {printf \"%.0f\", ($LOAD / $CORES) * 100}")

# Memory
MEM=$(awk '/MemTotal/{t=$2} /MemAvailable/{a=$2} END{printf "%.0f", (1-a/t)*100}' /proc/meminfo)

# Disk
DSK=$(df / | awk 'NR==2{print $5}')

# Assemble
SEP=" #[fg=colour241]|#[default] "
OUT=""
[ -n "$BAT" ] && OUT+="#[fg=colour114]BAT ${BAT}${SEP}"
OUT+="#[fg=colour208]CPU ${CPU}%${SEP}#[fg=colour228]MEM ${MEM}%${SEP}#[fg=colour246]DSK ${DSK}"

printf '%s' "$OUT"
