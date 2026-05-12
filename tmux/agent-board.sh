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

# Cross-platform stat helpers (macOS -f vs Linux -c).
_stat_mtime() { stat -f %m "$1" 2>/dev/null || stat -c %Y "$1" 2>/dev/null || echo 0; }
_stat_size()  { stat -f %z "$1" 2>/dev/null || stat -c %s "$1" 2>/dev/null || echo 0; }

# Named Python parsers for jsonl extraction.
_extract_ctx_tokens() {
  python3 -c '
import json,sys
try:
  d=json.loads(sys.stdin.read())
  u=(d.get("message") or {}).get("usage") or {}
  print((u.get("input_tokens") or 0)+(u.get("cache_read_input_tokens") or 0)+(u.get("cache_creation_input_tokens") or 0))
except Exception:
  print("")
' 2>/dev/null
}

_extract_cwd() {
  python3 -c '
import json,sys
try:
  d=json.loads(sys.stdin.read())
  print(d.get("cwd") or "")
except Exception:
  print("")
' 2>/dev/null
}

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

# Pick newest *.jsonl under a Claude Code session dir.
newest_jsonl() {
  local sess_dir=$1
  [[ -d "$sess_dir" ]] || { printf ''; return; }
  ls -t "$sess_dir"/*.jsonl 2>/dev/null | head -n1
}

# Sum input + cache_read + cache_creation tokens from the last usage block in a
# jsonl file. Cached by jsonl mtime+size at $cache_file so 2s ticks stay cheap.
_ctx_from_jsonl() {
  local latest=$1 cache_file=$2
  [[ -n "$latest" && -f "$latest" ]] || { printf ''; return; }
  local mtime size
  mtime=$(_stat_mtime "$latest")
  size=$(_stat_size "$latest")
  if [[ -f "$cache_file" ]]; then
    local cmtime csize ctokens
    IFS=: read -r cmtime csize ctokens < "$cache_file"
    if [[ "$cmtime" == "$mtime" && "$csize" == "$size" ]]; then
      printf '%s' "$ctokens"
      return
    fi
  fi
  local tokens
  tokens=$(tail -r "$latest" 2>/dev/null | grep -m1 '"usage"' | _extract_ctx_tokens)
  [[ -n "$tokens" ]] || tokens=0
  mkdir -p "$(dirname "$cache_file")" 2>/dev/null
  printf '%s:%s:%s\n' "$mtime" "$size" "$tokens" > "$cache_file" 2>/dev/null
  printf '%s' "$tokens"
}

# Live context size for a lane (worktree).
# Maps lane_dir → encoded session dir (~/.claude/projects/<dir>).
get_ctx_tokens() {
  local lane_dir=$1
  local enc=${lane_dir//\//-}
  enc=${enc//./-}
  local sess_dir="$HOME/.claude/projects/$enc"
  local latest cache_file
  latest=$(newest_jsonl "$sess_dir")
  [[ -n "$latest" ]] || { printf ''; return; }
  cache_file="$lane_dir/.claude/ctx-cache"
  _ctx_from_jsonl "$latest" "$cache_file"
}

# Live context size for a cockpit session (project session dir, no worktree).
get_ctx_tokens_session() {
  local session_dir=$1
  local latest
  latest=$(newest_jsonl "$session_dir")
  [[ -n "$latest" ]] || { printf ''; return; }
  _ctx_from_jsonl "$latest" "$session_dir/.ctx-cache"
}

# Pull cwd field from the first jsonl line that carries one (meta/summary
# lines often lack it). Cached at <session_dir>/.cwd-cache so we don't grep
# every tick.
get_cwd_from_jsonl() {
  local jsonl=$1
  [[ -f "$jsonl" ]] || { printf ''; return; }
  local sess_dir cache
  sess_dir=$(dirname "$jsonl")
  cache="$sess_dir/.cwd-cache"
  if [[ -f "$cache" ]]; then
    cat "$cache"
    return
  fi
  local cwd
  cwd=$(grep -m1 '"cwd"' "$jsonl" 2>/dev/null | _extract_cwd)
  [[ -n "$cwd" ]] && printf '%s' "$cwd" > "$cache" 2>/dev/null
  printf '%s' "$cwd"
}

fmt_ctx() {
  local n=${1:-}
  [[ -z "$n" || "$n" == 0 ]] && return
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

  local lane_dir pid_file raw state state_mtime age c pid is_stale
  lane_dir=$(dirname "$(dirname "$state_file")")
  pid_file="$lane_dir/.claude/agent-pid"

  raw=$(tail -n1 "$state_file" 2>/dev/null || echo "—")
  state_mtime=$(_stat_mtime "$state_file")
  age=$((now - state_mtime))

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
    # Reset state to IDLE but preserve mtime so the hide-idle threshold
    # measures from when the lane actually went quiet, not when the board noticed.
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

  printf '%s\t%s%-29s %-18s %s%s\n' \
    "$prio" "$c" "$display" "$state" "$ctx_disp" "$reset"
}

# Render a cockpit row for an active claude session not under any tracked
# worktree/main-repo path. Derives state from jsonl mtime when there's no
# agent-state file (cockpit dirs don't usually run our hooks).
render_cockpit_row() {
  local cwd=$1 session_dir=$2
  local latest age mtime now_local
  latest=$(newest_jsonl "$session_dir")
  [[ -n "$latest" ]] || return
  mtime=$(_stat_mtime "$latest")
  age=$((now - mtime))

  # Skip cockpit rows that haven't moved in >30 min — they're parked, not live.
  (( age > 1800 )) && [[ -z "${BOARD_SHOW_ALL:-}" ]] && return

  local state c
  if [[ -f "$cwd/.claude/agent-state" ]]; then
    state=$(tail -n1 "$cwd/.claude/agent-state" 2>/dev/null || echo IDLE)
    case "$state" in
      ACTIVE*) c=$green ;;
      WAITING*) c=$red; state="W:input" ;;
      DONE) c=$green ;;
      RUNNING*) c=$yellow ;;
      FAILED*) c=$red ;;
      *) c=$dim ;;
    esac
  else
    if (( age < 30 )); then state=ACTIVE; c=$green
    elif (( age < 300 )); then state=RECENT; c=$yellow
    else state=IDLE; c=$dim
    fi
  fi

  local label="$cwd"
  if [[ "$cwd" == "$HOME"* ]]; then
    label="~${cwd#$HOME}"
  fi
  [[ ${#label} -gt 28 ]] && label="…${label: -27}"

  local ctx ctx_disp
  ctx=$(get_ctx_tokens_session "$session_dir")
  ctx_disp=$(fmt_ctx "$ctx")

  local prio
  case "$state" in
    ACTIVE*)  prio=4 ;;
    RECENT)   prio=5 ;;
    *)        prio=6 ;;
  esac

  printf '%s\t%s%-29s %-18s %s%s\n' \
    "$prio" "$c" "$label" "$state" "$ctx_disp" "$reset"
}

print_section_header() {
  local title=$1
  printf '%s%-29s %-18s %s%s\n' \
    "$bold" "$title" "STATE" "CTX" "$reset"
}

# Build covered_cwds while iterating lanes so cockpit dedupes correctly.
# Use newline-delimited string (bash 3.2 has no associative arrays).
covered_cwds=$'\n'
note_covered() { covered_cwds+="$1"$'\n'; }
is_covered()   { [[ "$covered_cwds" == *$'\n'"$1"$'\n'* ]]; }

lane_rows=""
lane_count=0
for root in "${ROOTS[@]}"; do
  for repo_dir in "$root"/*/; do
    [[ -d "$repo_dir.git" || -f "$repo_dir.git" ]] || continue
    state_file="$repo_dir.claude/agent-state"
    [[ -f "$state_file" ]] || continue
    lane_count=$((lane_count + 1))
    repo=$(basename "${repo_dir%/}")
    note_covered "${repo_dir%/}"
    lane_rows+=$(render_row "$state_file" "$repo/(main)")$'\n'
  done

  for wt in "$root"/*/.claude/worktrees/*/; do
    [[ -d "$wt" ]] || continue
    state_file="$wt.claude/agent-state"
    [[ -f "$state_file" ]] || continue
    lane_count=$((lane_count + 1))
    name=$(basename "${wt%/}")
    repo=$(basename "$(dirname "$(dirname "$(dirname "${wt%/}")")")")
    note_covered "${wt%/}"
    lane_rows+=$(render_row "$state_file" "$repo/$name")$'\n'
  done
done

# Cockpit pass: any active Claude session whose cwd isn't already a tracked
# lane. Window = jsonl mtime within COCKPIT_ACTIVE_SECS (default 5 min).
COCKPIT_ACTIVE_SECS=${COCKPIT_ACTIVE_SECS:-300}
cockpit_rows=""
cockpit_count=0
for sess_dir in "$HOME"/.claude/projects/*/; do
  [[ -d "$sess_dir" ]] || continue
  latest=$(newest_jsonl "${sess_dir%/}")
  [[ -n "$latest" ]] || continue
  mt=$(_stat_mtime "$latest")
  (( now - mt <= COCKPIT_ACTIVE_SECS )) || continue
  cwd=$(get_cwd_from_jsonl "$latest")
  [[ -n "$cwd" ]] || continue
  is_covered "$cwd" && continue
  cockpit_count=$((cockpit_count + 1))
  cockpit_rows+=$(render_cockpit_row "$cwd" "${sess_dir%/}")$'\n'
done

if (( lane_count == 0 && cockpit_count == 0 )); then
  printf '%s(no worktrees or active cockpit sessions)%s\n' "$dim" "$reset"
  exit 0
fi

print_section_header "LANES"
if (( lane_count > 0 )); then
  printf '%s' "$lane_rows" | grep -v '^$' | sort -k1,1n | cut -f2-
else
  printf '%s(none)%s\n' "$dim" "$reset"
fi

if (( cockpit_count > 0 )); then
  printf '\n'
  print_section_header "COCKPIT"
  printf '%s' "$cockpit_rows" | grep -v '^$' | sort -k1,1n | cut -f2-
fi
