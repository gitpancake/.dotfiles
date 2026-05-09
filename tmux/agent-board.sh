#!/usr/bin/env bash
# agent-board — single-pane status board for parallel worktree agents.
#
# Pin in a tmux pane with:
#   watch -tcn2 ~/.tmux/agent-board.sh
#
# Reads <worktree>/.claude/agent-state (written by hook scripts) and prints
# one row per worktree, color-coded by state. Goes red when an agent needs
# attention; otherwise stays out of your way.

set -u

# Roots scanned for worktrees. Add more as needed.
ROOTS=("${HOME}/Documents/code")

reset=$'\033[0m'
red=$'\033[31m'
green=$'\033[32m'
yellow=$'\033[33m'
dim=$'\033[2m'
bold=$'\033[1m'

now=$(date +%s)

# Reason-code vocab. Mirrors ~/.claude/agent-state-vocab.md.
# Returns class (red|yellow|dim) for a code, empty if unknown.
class_for_code() {
  case "$1" in
    ambiguity|creds|test-loop|merge-conflict|verify|scope|input) printf 'red' ;;
    external) printf 'yellow' ;;
    review)   printf 'dim' ;;
    *)        printf '' ;;
  esac
}

humanAge() {
  local s=$1
  if   (( s < 60 ));    then printf '%ds' "$s"
  elif (( s < 3600 ));  then printf '%dm' $((s/60))
  elif (( s < 86400 )); then printf '%dh' $((s/3600))
  else                       printf '%dd' $((s/86400))
  fi
}

# Sort priority: lower number = higher up the board.
priority_for() {
  local state=$1 class=$2
  case "$state" in
    WAITING*)
      case "$class" in
        red)    printf '0' ;;
        yellow) printf '2' ;;
        dim)    printf '5' ;;
        *)      printf '0' ;;
      esac
      ;;
    FAILED*)  printf '1' ;;
    RUNNING*) printf '3' ;;
    ACTIVE*)  printf '4' ;;
    STALE*)   printf '5' ;;
    DONE)     printf '6' ;;
    IDLE)     printf '6' ;;
    *)        printf '4' ;;
  esac
}

shopt -s nullglob 2>/dev/null || true

# Live context size for a lane.
# Maps lane_dir → encoded session dir (~/.claude/projects/<dir>), reads the
# newest *.jsonl, and sums input+cache_read+cache_creation tokens from the last
# assistant message's usage block. Cached by jsonl mtime+size to keep ticks fast.
get_ctx_tokens() {
  local lane_dir=$1
  local enc=${lane_dir//\//-}
  enc=${enc//./-}
  local sess_dir="$HOME/.claude/projects/$enc"
  [[ -d "$sess_dir" ]] || { printf ''; return; }
  local latest
  latest=$(ls -t "$sess_dir"/*.jsonl 2>/dev/null | head -n1)
  [[ -n "$latest" ]] || { printf ''; return; }
  local mtime size cache_file
  mtime=$(stat -f %m "$latest" 2>/dev/null || echo 0)
  size=$(stat -f %z "$latest" 2>/dev/null || echo 0)
  cache_file="$lane_dir/.claude/ctx-cache"
  if [[ -f "$cache_file" ]]; then
    local cached cmtime csize ctokens
    IFS=: read -r cmtime csize ctokens < "$cache_file"
    if [[ "$cmtime" == "$mtime" && "$csize" == "$size" ]]; then
      printf '%s' "$ctokens"
      return
    fi
  fi
  local tokens
  tokens=$(tail -r "$latest" 2>/dev/null | grep -m1 '"usage"' | python3 -c '
import json,sys
try:
  d=json.loads(sys.stdin.read())
  u=(d.get("message") or {}).get("usage") or {}
  print((u.get("input_tokens") or 0)+(u.get("cache_read_input_tokens") or 0)+(u.get("cache_creation_input_tokens") or 0))
except Exception:
  print("")
' 2>/dev/null)
  [[ -n "$tokens" ]] || tokens=0
  printf '%s:%s:%s\n' "$mtime" "$size" "$tokens" > "$cache_file" 2>/dev/null
  printf '%s' "$tokens"
}

fmt_ctx() {
  local n=${1:-}
  [[ -z "$n" || "$n" == 0 ]] && { printf '-'; return; }
  if   (( n < 1000 ));    then printf '%d' "$n"
  elif (( n < 1000000 )); then printf '%dK' $((n/1000))
  else
    local tenths=$((n/100000))
    printf '%d.%dM' $((tenths/10)) $((tenths%10))
  fi
}

# Stale threshold for transient states (ACTIVE/WAITING/RUNNING) when no live
# claude PID is recorded. 5 minutes — long enough to outlast normal tool calls.
STALE_AFTER_SECS=300

# Hide IDLE rows older than this. Override with BOARD_HIDE_IDLE_AFTER=<secs>
# or BOARD_SHOW_ALL=1 to disable hiding.
HIDE_IDLE_AFTER=${BOARD_HIDE_IDLE_AFTER:-1800}

# Render one row to stdout, prefixed with sort key + tab so callers can sort.
render_row() {
  local state_file=$1 label=$2
  [[ -f "$state_file" ]] || return

  local lane_dir port_file pid_file raw state state_mtime age port c pid is_stale
  lane_dir=$(dirname "$(dirname "$state_file")")
  port_file="$lane_dir/.env.local.port"
  pid_file="$lane_dir/.claude/agent-pid"

  raw=$(tail -n1 "$state_file" 2>/dev/null || echo "—")
  state_mtime=$(stat -f %m "$state_file" 2>/dev/null || echo "$now")
  age=$((now - state_mtime))
  port=$(grep -oE '[0-9]+' "$port_file" 2>/dev/null | head -n1 || echo "-")

  # Hide stale IDLE rows. Active/waiting/failed/done always render.
  if [[ -z "${BOARD_SHOW_ALL:-}" && "$raw" == "IDLE" && $age -gt $HIDE_IDLE_AFTER ]]; then
    return
  fi

  # Parse WAITING into code. Detail is in the state file (cat it if you care).
  # Board shows compact `W:<code>` only.
  local state=$raw class=""
  if [[ "$raw" =~ ^WAITING:([^:]+):(.*)$ ]]; then
    local code=${BASH_REMATCH[1]}
    class=$(class_for_code "$code")
    if [[ -n "$class" ]]; then
      state="W:${code}"
    else
      class=red
      state="W:input"
    fi
  elif [[ "$raw" =~ ^WAITING:(.+)$ ]]; then
    class=red
    state="W:input"
  fi

  # Liveness check.
  is_stale=0
  case "$raw" in
    ACTIVE*|WAITING*|RUNNING*)
      if [[ -f "$pid_file" ]]; then
        pid=$(cat "$pid_file" 2>/dev/null)
        if [[ -n "$pid" ]] && ! kill -0 "$pid" 2>/dev/null; then
          is_stale=1
        fi
      elif (( age > STALE_AFTER_SECS )); then
        is_stale=1
      fi
      ;;
  esac

  if (( is_stale )); then
    # Self-heal: claude exited without firing Stop (terminal close, kill, crash).
    # Reset state to IDLE but preserve mtime so AGE still reflects when the
    # lane actually went quiet, not when the board noticed.
    echo "IDLE" > "$state_file"
    touch -t "$(date -r "$state_mtime" '+%Y%m%d%H%M.%S')" "$state_file" 2>/dev/null || true
    rm -f "$pid_file"
    state="IDLE"
    c=$dim
    class=""
  else
    case "$state" in
      WAITING*)
        case "$class" in
          red)    c=$red ;;
          yellow) c=$yellow ;;
          dim)    c=$dim ;;
          *)      c=$red ;;
        esac
        ;;
      FAILED*)  c=$red ;;
      ACTIVE*)  c=$green ;;
      DONE)     c=$green ;;
      RUNNING*) c=$yellow ;;
      IDLE)     c=$dim ;;
      *)        c=$yellow ;;
    esac
  fi

  # Prefer cached LLM summary keyed by HEAD sha; fall back to HEAD subject.
  local display sha cache_sha cache_text
  sha=$(git -C "$lane_dir" rev-parse HEAD 2>/dev/null)
  local cache="$lane_dir/.claude/summary"
  if [[ -n "$sha" && -f "$cache" ]]; then
    cache_sha=$(head -1 "$cache" 2>/dev/null)
    if [[ "$cache_sha" == "$sha" ]]; then
      cache_text=$(sed -n '2p' "$cache")
      display="$cache_text"
    fi
  fi
  if [[ -z "${display:-}" ]]; then
    display=$(git -C "$lane_dir" log -1 --pretty=%s 2>/dev/null || true)
    # Fork background refresh so next render picks up the LLM summary.
    # Skip idle/done/failed lanes — no point summarizing dormant work.
    if [[ -n "$sha" && -z "${BOARD_NO_SUMMARY:-}" ]]; then
      case "$raw" in
        IDLE|DONE|FAILED*) ;;
        *) ("$HOME/.claude/scripts/lane-summary.sh" "$lane_dir" "$sha" </dev/null >/dev/null 2>&1 &) ;;
      esac
    fi
  fi
  [[ -z "$display" ]] && display="$label"
  [[ ${#display} -gt 28 ]] && display="${display:0:25}..."

  local prio
  if (( is_stale )); then
    prio=5
  else
    prio=$(priority_for "$raw" "$class")
  fi

  local ctx ctx_disp
  ctx=$(get_ctx_tokens "$lane_dir")
  ctx_disp=$(fmt_ctx "$ctx")

  printf '%s\t%s%-29s %-18s %-6s %-6s %s%s\n' \
    "$prio" "$c" "$display" "$state" "$(humanAge "$age")" "$ctx_disp" "$port" "$reset"
}

printf '%s%-29s %-18s %-6s %-6s %s%s\n' \
  "$bold" "LANE" "STATE" "AGE" "CTX" "PORT" "$reset"
printf '%s%s%s\n' "$dim" "----------------------------------------------------------------" "$reset"

rows=""
count=0
for root in "${ROOTS[@]}"; do
  for repo_dir in "$root"/*/; do
    [[ -d "$repo_dir.git" || -f "$repo_dir.git" ]] || continue
    state_file="$repo_dir.claude/agent-state"
    [[ -f "$state_file" ]] || continue
    count=$((count + 1))
    repo=$(basename "${repo_dir%/}")
    rows+=$(render_row "$state_file" "$repo/(main)")$'\n'
  done

  for wt in "$root"/*/.claude/worktrees/*/; do
    [[ -d "$wt" ]] || continue
    state_file="$wt.claude/agent-state"
    [[ -f "$state_file" ]] || continue
    count=$((count + 1))
    name=$(basename "${wt%/}")
    repo=$(basename "$(dirname "$(dirname "$(dirname "${wt%/}")")")")
    rows+=$(render_row "$state_file" "$repo/$name")$'\n'
  done
done

if (( count == 0 )); then
  printf '%s(no worktrees found under: %s)%s\n' \
    "$dim" "${ROOTS[*]}" "$reset"
  exit 0
fi

# Drop blanks (hidden rows leave empty lines), sort by priority, strip key.
printf '%s' "$rows" | grep -v '^$' | sort -k1,1n | cut -f2-
