#!/bin/zsh
set -u

export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

LOGDIR="$HOME/.claude/linkedin-logs"
mkdir -p "$LOGDIR"

TODAY=$(date +%F)
WINDOW_START=$(date -v-7d +%F)
DRY_RUN="${DRY_RUN:-0}"
PROMPT_FILE="$HOME/.dotfiles/scripts/weekly-linkedin.prompt.md"
LOG="$LOGDIR/run-$TODAY.log"

if [ ! -f "$PROMPT_FILE" ]; then
    echo "$(date) ERROR: prompt file missing: $PROMPT_FILE" >> "$LOG"
    exit 1
fi

set -a
[ -f "$HOME/.claude/.env" ] && . "$HOME/.claude/.env"
set +a

AUTOPUBLISH="${LINKEDIN_AUTOPUBLISH:-0}"

if [ "$DRY_RUN" = "0" ] && [ -z "${ORDINAL_API_KEY:-}" ]; then
    echo "$(date) ERROR: ORDINAL_API_KEY not set in ~/.claude/.env; run with DRY_RUN=1 or add the key" >> "$LOG"
    exit 1
fi

slot() { date -v+"$1"d -v9H -v0M -v0S +"%Y-%m-%d %H:%M"; }
DOW=$(date +%u)
TUE=$(( (2 - DOW + 7) % 7 )); [ "$TUE" = "0" ] && TUE=7
THU=$(( (4 - DOW + 7) % 7 )); [ "$THU" = "0" ] && THU=7
SAT=$(( (6 - DOW + 7) % 7 )); [ "$SAT" = "0" ] && SAT=7

HEADER="RUN CONTEXT (auto-computed, do not recompute):
- TODAY=$TODAY
- WINDOW_START=$WINDOW_START
- SLOTS (local time): $(slot $TUE) | $(slot $THU) | $(slot $SAT)
- LOGDIR=$LOGDIR
- DRY_RUN=$DRY_RUN
- AUTOPUBLISH=$AUTOPUBLISH

"
FULL_PROMPT="$HEADER$(cat "$PROMPT_FILE")"

echo "=== $(date) starting weekly linkedin drafts: window $WINDOW_START..$TODAY dry_run=$DRY_RUN autopublish=$AUTOPUBLISH ===" >> "$LOG"

cd "$HOME"
claude -p "$FULL_PROMPT" \
    --dangerously-skip-permissions \
    --model claude-fable-5 \
    >> "$LOG" 2>&1

echo "=== $(date) finished (exit $?) ===" >> "$LOG"
