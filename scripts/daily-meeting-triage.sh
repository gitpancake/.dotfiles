#!/bin/zsh
# Daily meeting-triage v2: pull Granola + Pocket, enrich existing ENGH/AO Linear work
# (comments, project updates, bugs routed into active projects). Never creates feature
# tickets. Invoked by launchd (ai.cartage.meeting-triage) every weekday at 12:00.
set -u

export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

LOGDIR="$HOME/.claude/meeting-triage-logs"
mkdir -p "$LOGDIR"

TODAY=$(date +%F)
DOW=$(date +%u)                       # 1=Mon .. 7=Sun
if [ "$DOW" = "1" ]; then LOOKBACK=3; else LOOKBACK=1; fi   # Monday covers Fri+weekend
WINDOW_START=$(date -v-${LOOKBACK}d +%F)
WINDOW_END=$(date -v-1d +%F)

PROMPT_FILE="$HOME/.dotfiles/scripts/daily-meeting-triage.prompt.md"
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

"
FULL_PROMPT="$HEADER$(cat "$PROMPT_FILE")"

echo "=== $(date) starting triage: window $WINDOW_START..$WINDOW_END (since-days $LOOKBACK) ===" >> "$LOG"

cd "$HOME"
claude -p "$FULL_PROMPT" \
    --dangerously-skip-permissions \
    --model claude-fable-5 \
    >> "$LOG" 2>&1

echo "=== $(date) finished (exit $?) ===" >> "$LOG"
