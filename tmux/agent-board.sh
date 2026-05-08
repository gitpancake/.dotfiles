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

humanAge() {
  local s=$1
  if   (( s < 60 ));    then printf '%ds' "$s"
  elif (( s < 3600 ));  then printf '%dm' $((s/60))
  elif (( s < 86400 )); then printf '%dh' $((s/3600))
  else                       printf '%dd' $((s/86400))
  fi
}

printf '%s%-36s %-18s %-8s %s%s\n' \
  "$bold" "LANE" "STATE" "AGE" "PORT" "$reset"
printf '%s%s%s\n' "$dim" "------------------------------------------------------------------------" "$reset"

shopt -s nullglob 2>/dev/null || true

# Stale threshold for transient states (ACTIVE/WAITING/RUNNING) when no live
# claude PID is recorded. 5 minutes — long enough to outlast normal tool calls.
STALE_AFTER_SECS=300

# Print a single row given a state file path.
print_row() {
  local state_file=$1 label=$2
  [[ -f "$state_file" ]] || return

  local lane_dir port_file pid_file state state_mtime age port c pid is_stale
  lane_dir=$(dirname "$(dirname "$state_file")")
  port_file="$lane_dir/.env.local.port"
  pid_file="$lane_dir/.claude/agent-pid"

  state=$(tail -n1 "$state_file" 2>/dev/null || echo "—")
  state_mtime=$(stat -f %m "$state_file" 2>/dev/null || echo "$now")
  age=$((now - state_mtime))
  port=$(grep -oE '[0-9]+' "$port_file" 2>/dev/null | head -n1 || echo "-")

  # Liveness check.
  is_stale=0
  case "$state" in
    ACTIVE*|WAITING*|RUNNING*)
      if [[ -f "$pid_file" ]]; then
        pid=$(cat "$pid_file" 2>/dev/null)
        if [[ -n "$pid" ]] && ! kill -0 "$pid" 2>/dev/null; then
          is_stale=1
        fi
      elif (( age > STALE_AFTER_SECS )); then
        # No pid recorded (legacy state file or hook couldn't find claude) — fall
        # back to age. Transient state stuck for >5min is almost certainly orphaned.
        is_stale=1
      fi
      ;;
  esac

  if (( is_stale )); then
    state="STALE:${state%%:*}"
    c=$dim
  else
    case "$state" in
      WAITING*) c=$red ;;
      FAILED*)  c=$red ;;
      ACTIVE*)  c=$green ;;
      DONE)     c=$green ;;
      RUNNING*) c=$yellow ;;
      IDLE)     c=$dim ;;
      *)        c=$yellow ;;
    esac
  fi

  # Show HEAD commit subject; fall back to lane slug if git fails.
  local display
  display=$(git -C "$lane_dir" log -1 --pretty=%s 2>/dev/null || true)
  [[ -z "$display" ]] && display="$label"
  [[ ${#display} -gt 35 ]] && display="${display:0:32}..."

  printf '%s%-36s %-18s %-8s %s%s\n' \
    "$c" "$display" "$state" "$(humanAge "$age")" "$port" "$reset"
}

count=0
for root in "${ROOTS[@]}"; do
  # Main checkouts: state file at <repo>/.claude/agent-state.
  # Skip dirs that are themselves a worktree (their parent has a sibling .git
  # worktrees dir); easier signal: presence of a .git directory or file.
  for repo_dir in "$root"/*/; do
    [[ -d "$repo_dir.git" || -f "$repo_dir.git" ]] || continue
    state_file="$repo_dir.claude/agent-state"
    [[ -f "$state_file" ]] || continue
    count=$((count + 1))
    repo=$(basename "${repo_dir%/}")
    print_row "$state_file" "$repo/(main)"
  done

  # Worktree lanes under <repo>/.claude/worktrees/<lane>/.
  for wt in "$root"/*/.claude/worktrees/*/; do
    [[ -d "$wt" ]] || continue
    state_file="$wt.claude/agent-state"
    [[ -f "$state_file" ]] || continue
    count=$((count + 1))
    name=$(basename "${wt%/}")
    repo=$(basename "$(dirname "$(dirname "$(dirname "${wt%/}")")")")
    print_row "$state_file" "$repo/$name"
  done
done

if (( count == 0 )); then
  printf '%s(no worktrees found under: %s)%s\n' \
    "$dim" "${ROOTS[*]}" "$reset"
fi
