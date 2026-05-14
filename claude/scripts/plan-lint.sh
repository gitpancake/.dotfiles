#!/bin/bash
# plan-lint.sh <TICKET>
#
# Thin entry point. Resolves plan path; if missing, exits 2.
# Otherwise prints a header instructing the caller to dispatch the
# `plan-lint` subagent. Verdict goes to ~/.claude/plans/<TICKET>.lint.md.

set -u

if [ $# -lt 1 ]; then
  printf 'usage: plan-lint.sh <TICKET>\n' >&2
  exit 2
fi

TICKET=$(printf '%s' "$1" | tr '[:lower:]' '[:upper:]')
PLAN_PATH="$HOME/.claude/plans/${TICKET}.md"
VERDICT_PATH="$HOME/.claude/plans/${TICKET}.lint.md"

if [ ! -f "$PLAN_PATH" ]; then
  printf 'plan-lint: no plan at %s\n' "$PLAN_PATH" >&2
  printf '(plan-lint is dormant under the sync/Ralph workflow — write a plan there to use it)\n' >&2
  exit 2
fi

# Memoization: if verdict newer than plan, reuse the cached result.
# Bypass with PLAN_LINT_FORCE=1.
mtime() {
  stat -f %m "$1" 2>/dev/null || stat -c %Y "$1" 2>/dev/null || printf '0'
}

if [ -z "${PLAN_LINT_FORCE:-}" ] && [ -f "$VERDICT_PATH" ]; then
  PLAN_MTIME=$(mtime "$PLAN_PATH")
  VERDICT_MTIME=$(mtime "$VERDICT_PATH")
  if [ "$VERDICT_MTIME" -ge "$PLAN_MTIME" ]; then
    cat <<EOF
plan-lint: CACHED (verdict newer than plan)
  TICKET=$TICKET
  VERDICT_PATH=$VERDICT_PATH

Skip subagent dispatch. Read VERDICT_PATH directly.
To force re-lint, set PLAN_LINT_FORCE=1.
EOF
    exit 0
  fi
fi

cat <<EOF
plan-lint gate for $TICKET

Dispatch the \`plan-lint\` subagent (Agent tool, subagent_type: "plan-lint") with:
  TICKET=$TICKET
  PLAN_PATH=$PLAN_PATH
  VERDICT_PATH=$VERDICT_PATH

Subagent reads the plan + Linear ticket, writes verdict to VERDICT_PATH.
After dispatch, read VERDICT_PATH. Status: PASS → continue. Status: FAIL → stop and surface gaps.
EOF
