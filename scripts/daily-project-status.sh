#!/bin/zsh
set -u

export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

LOGDIR="$HOME/.claude/project-status-logs"
mkdir -p "$LOGDIR"

TODAY=$(date +%F)
DOW=$(date +%u)
if [ "$DOW" = "1" ]; then LOOKBACK=3; else LOOKBACK=1; fi
WINDOW_START=$(date -v-${LOOKBACK}d +%F)
WINDOW_END=$(date -v-1d +%F)
ACTIVITY_FLOOR=$(date -u -v-7d +%Y-%m-%dT%H:%M:%SZ)
DRY_RUN="${DRY_RUN:-0}"

PROMPT_FILE="$HOME/.dotfiles/scripts/daily-project-status.prompt.md"
LOG="$LOGDIR/run-$TODAY.log"

if [ ! -f "$PROMPT_FILE" ]; then
    echo "$(date) ERROR: prompt file missing: $PROMPT_FILE" >> "$LOG"
    exit 1
fi

set -a
[ -f "$HOME/.claude/.env" ] && . "$HOME/.claude/.env"
set +a

HEADER="RUN CONTEXT (auto-computed, do not recompute):
- TODAY=$TODAY (weekday $DOW)
- GRANOLA_SINCE_DAYS=$LOOKBACK
- WINDOW_START=$WINDOW_START
- WINDOW_END=$WINDOW_END
- ACTIVITY_FLOOR=$ACTIVITY_FLOOR
- LOGDIR=$LOGDIR
- DRY_RUN=$DRY_RUN

"
FULL_PROMPT="$HEADER$(cat "$PROMPT_FILE")"

echo "=== $(date) starting project status: window $WINDOW_START..$WINDOW_END dry_run=$DRY_RUN ===" >> "$LOG"

cd "$HOME"
claude -p "$FULL_PROMPT" \
    --dangerously-skip-permissions \
    --model claude-fable-5 \
    >> "$LOG" 2>&1

echo "=== $(date) finished (exit $?) ===" >> "$LOG"
