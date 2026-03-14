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

# Dynamic color: green → yellow → orange → red based on severity
# For "higher is worse" metrics (CPU, MEM, DSK): low=green, high=red
# For battery: inverted — high=green, low=red
severity_color() {
  local val=$1
  if [ "$val" -le 25 ]; then echo "colour114"    # green
  elif [ "$val" -le 50 ]; then echo "colour228"   # yellow
  elif [ "$val" -le 75 ]; then echo "colour208"   # orange
  else echo "colour196"                            # red
  fi
}

bat_color() {
  local val=$1
  if [ "$val" -ge 75 ]; then echo "colour114"     # green
  elif [ "$val" -ge 50 ]; then echo "colour228"   # yellow
  elif [ "$val" -ge 25 ]; then echo "colour208"   # orange
  else echo "colour196"                            # red
  fi
}

# Assemble
SEP=" #[fg=colour241]|#[default] "
OUT=""
if [ -n "$BAT" ]; then
  BAT_PCT=${BAT%%%*}
  OUT+="#[fg=$(bat_color "$BAT_PCT")]BAT ${BAT}${SEP}"
fi
OUT+="#[fg=$(severity_color "$CPU")]CPU ${CPU}%${SEP}"
OUT+="#[fg=$(severity_color "$MEM")]MEM ${MEM}%${SEP}"
DSK_NUM=${DSK%%%}
OUT+="#[fg=$(severity_color "$DSK_NUM")]DSK ${DSK}"

printf '%s' "$OUT"
