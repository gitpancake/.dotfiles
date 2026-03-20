#!/usr/bin/env bash

OS="$(uname -s)"

# Battery
BAT=""
if [ "$OS" = "Darwin" ]; then
  BAT_INFO=$(pmset -g batt 2>/dev/null)
  PCT=$(echo "$BAT_INFO" | grep -oE '[0-9]+%' | head -1 | tr -d '%')
  if [ -n "$PCT" ]; then
    if echo "$BAT_INFO" | grep -q "AC Power"; then
      BAT="${PCT}%+"
    else
      BAT="${PCT}%"
    fi
  fi
else
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
fi

# CPU (load average shown as load/cores)
if [ "$OS" = "Darwin" ]; then
  CORES=$(sysctl -n hw.ncpu)
  LOAD=$(sysctl -n vm.loadavg | awk '{print $2}')
else
  CORES=$(nproc)
  LOAD=$(awk '{print $1}' /proc/loadavg)
fi
CPU_PCT=$(awk "BEGIN {printf \"%.0f\", ($LOAD / $CORES) * 100}")
CPU_LABEL=$(awk "BEGIN {printf \"%.1f/%d\", $LOAD, $CORES}")

# Memory
if [ "$OS" = "Darwin" ]; then
  PAGE_SIZE=$(sysctl -n hw.pagesize)
  TOTAL_MEM=$(sysctl -n hw.memsize)
  # Single vm_stat call, parse all three page counts at once
  eval "$(vm_stat | awk '
    /Pages free:/        {gsub(/\./,"",$3); printf "PAGES_FREE=%s\n",$3}
    /Pages inactive:/    {gsub(/\./,"",$3); printf "PAGES_INACTIVE=%s\n",$3}
    /Pages speculative:/ {gsub(/\./,"",$3); printf "PAGES_SPECULATIVE=%s\n",$3}
  ')"
  AVAILABLE=$(( (PAGES_FREE + PAGES_INACTIVE + PAGES_SPECULATIVE) * PAGE_SIZE ))
  MEM=$(awk "BEGIN {printf \"%.0f\", (1 - $AVAILABLE / $TOTAL_MEM) * 100}")
else
  MEM=$(awk '/MemTotal/{t=$2} /MemAvailable/{a=$2} END{printf "%.0f", (1-a/t)*100}' /proc/meminfo)
fi

# Disk
if [ "$OS" = "Darwin" ]; then
  DSK=$(df /System/Volumes/Data | awk 'NR==2{print $5}')
else
  DSK=$(df / | awk 'NR==2{print $5}')
fi

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
OUT+="#[fg=$(severity_color "$CPU_PCT")]CPU ${CPU_LABEL}${SEP}"
OUT+="#[fg=$(severity_color "$MEM")]MEM ${MEM}%${SEP}"
DSK_NUM=${DSK%%%}
OUT+="#[fg=$(severity_color "$DSK_NUM")]DSK ${DSK}"

printf '%s' "$OUT"
