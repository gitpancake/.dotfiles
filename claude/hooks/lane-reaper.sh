#!/usr/bin/env bash
# lane-reaper.sh — SessionEnd hook.
#
# Closes the orphan-build-proc leak: lane Claude dies (turn-cap, OOM, /clear,
# SIGKILL) while a `bun type-check` / vitest / jest / playwright child is
# mid-flight. The child reparents to launchd and keeps running with 4GB+ RSS
# until the user notices and `kill`s it by hand.
#
# This hook runs at SessionEnd. It only engages when cwd is inside a wt lane
# (.claude/worktrees/<lane>/), then SIGTERMs any tsc/vitest/jest/playwright
# process whose own cwd is under the lane path. SIGKILL follows after 3s if
# still alive.
#
# Pure shell; no LLM call. Reads SessionEnd JSON from stdin for cwd.

set -u

payload=""
if [[ ! -t 0 ]]; then
  payload="$(cat || true)"
fi

cwd=""
if [[ -n "$payload" ]] && command -v jq >/dev/null 2>&1; then
  cwd="$(printf '%s' "$payload" | jq -r '.cwd // empty' 2>/dev/null || true)"
fi
[[ -z "$cwd" ]] && cwd="$PWD"

case "$cwd" in
  */.claude/worktrees/*) ;;
  *) exit 0 ;;
esac

# Canonicalize so prefix-match isn't fooled by symlinks / trailing slashes.
lane_root="$(cd "$cwd" 2>/dev/null && pwd -P)" || exit 0
[[ -n "$lane_root" ]] || exit 0

log_dir="$HOME/.claude/logs"
log_file="$log_dir/lane-reaper.log"
mkdir -p "$log_dir"
log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$log_file"
}

# Find candidate procs. Matches the build tools that cost real memory.
# Use awk on `ps` rather than pgrep -f so we control the regex precisely.
# Stick to POSIX bash 3.2 features (no mapfile) — macOS ships /bin/bash 3.2.
candidates=$(
  ps -axo pid=,command= 2>/dev/null \
    | awk '
        /tsc --noEmit/ ||
        /tsc -b/ ||
        /vitest( |$)/ ||
        /jest( |$)/ ||
        /playwright (test|run)/ {
          print $1
        }
      '
)

[[ -z "$candidates" ]] && exit 0

reap=()
for pid in $candidates; do
  [[ "$pid" =~ ^[0-9]+$ ]] || continue
  # Resolve the target proc's cwd; lsof is the portable way on macOS.
  # `-a` ANDs filters; `-Fn` prints the name field for FD entries.
  pcwd="$(lsof -p "$pid" -a -d cwd -Fn 2>/dev/null \
            | awk '/^n/{print substr($0,2); exit}')"
  [[ -z "$pcwd" ]] && continue
  case "$pcwd" in
    "$lane_root"|"$lane_root"/*) reap+=("$pid") ;;
  esac
done

[[ ${#reap[@]} -eq 0 ]] && exit 0

log "lane=$lane_root reaping pids: ${reap[*]}"
kill -TERM "${reap[@]}" 2>/dev/null || true

# Brief grace, then SIGKILL stragglers. Don't sleep long — SessionEnd is
# on the user's exit path.
sleep 3
stragglers=()
for pid in "${reap[@]}"; do
  if kill -0 "$pid" 2>/dev/null; then
    stragglers+=("$pid")
  fi
done
if [[ ${#stragglers[@]} -gt 0 ]]; then
  log "lane=$lane_root SIGKILL stragglers: ${stragglers[*]}"
  kill -KILL "${stragglers[@]}" 2>/dev/null || true
fi

exit 0
