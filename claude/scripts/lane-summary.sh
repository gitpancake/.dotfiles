#!/usr/bin/env bash
# lane-summary — generate a one-line semantic summary of what a lane is doing.
#
# Cached at <wt>/.claude/summary as:
#   <sha>
#   <summary text>
#
# Cache is invalidated when HEAD sha changes (i.e. on commit). Board reads the
# cache cheaply; this script refreshes it in the background.
#
# Usage:
#   lane-summary.sh <wt-path> [<expected-sha>]
#
# If expected-sha is given and no longer matches HEAD, the script aborts (the
# lane moved on; another invocation will be queued).

set -u

wt=${1:?usage: lane-summary.sh <wt-path> [<sha>]}
expect=${2:-}

[[ -d "$wt" ]] || exit 0

cache="$wt/.claude/summary"
mkdir -p "$wt/.claude"

# Skip idle lanes — no point burning Haiku cycles on dormant agents.
state=$(tail -n1 "$wt/.claude/agent-state" 2>/dev/null || echo "")
case "$state" in
  IDLE|DONE|FAILED*) exit 0 ;;
esac

sha=$(git -C "$wt" rev-parse HEAD 2>/dev/null)
[[ -z "$sha" ]] && exit 0
[[ -n "$expect" && "$expect" != "$sha" ]] && exit 0

# Don't refresh if cache already matches sha.
if [[ -f "$cache" ]] && [[ "$(head -1 "$cache" 2>/dev/null)" == "$sha" ]]; then
  exit 0
fi

# Avoid stampede: only one summarizer per lane at a time.
lock="$wt/.claude/summary.lock"
if ! mkdir "$lock" 2>/dev/null; then
  exit 0
fi
trap 'rmdir "$lock" 2>/dev/null || true' EXIT

branch=$(git -C "$wt" rev-parse --abbrev-ref HEAD 2>/dev/null)
head_msg=$(git -C "$wt" log -1 --pretty=%s 2>/dev/null)
recent=$(git -C "$wt" log -5 --pretty='%h %s' 2>/dev/null)

# Pull plan if a Linear-style ticket is in the branch name.
plan_excerpt=""
if [[ "$branch" =~ ([A-Za-z]+-[0-9]+) ]]; then
  ticket=$(printf '%s' "${BASH_REMATCH[1]}" | tr '[:lower:]' '[:upper:]')
  plan="$HOME/.claude/plans/${ticket}.md"
  if [[ -f "$plan" ]]; then
    # First 60 lines is enough for slice list + AC.
    plan_excerpt=$(head -60 "$plan")
  fi
fi

prompt=$(printf 'Summarize what this coding-agent worktree is currently working on. Output rules:\n- max 25 chars\n- no ticket ID, no quotes, no prefix, no trailing punctuation\n- lowercase except acronyms\n- verb-noun shape (e.g. "rewrite shopify webhook", "fix tests on Slack handler")\n\nBranch: %s\nState: %s\nHEAD subject: %s\n\nRecent commits:\n%s\n\nPlan excerpt:\n%s\n' \
  "$branch" "$state" "$head_msg" "$recent" "${plan_excerpt:-(no plan)}")

summary=$(printf '%s' "$prompt" \
  | claude --print --model haiku 2>/dev/null \
  | head -1 \
  | tr -d '\n' \
  | cut -c1-28)

[[ -z "$summary" ]] && exit 0

# Re-check sha — lane may have committed during the LLM call.
new_sha=$(git -C "$wt" rev-parse HEAD 2>/dev/null)
[[ "$new_sha" != "$sha" ]] && exit 0

printf '%s\n%s\n' "$sha" "$summary" > "$cache"
