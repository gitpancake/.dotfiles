#!/usr/bin/env bash
# PreToolUse hook (matcher: mcp__linear-server__save_issue): block ad-hoc Linear
# issue creation. Source of truth for tickets is $TICKETS_DIR (local tree), not
# Linear — see global CLAUDE.md "Ticket Lifecycle". Linear is a write-only sink:
# the ONLY sanctioned write is /ship posting the PR link on an opened PR.
#
# Why: the model keeps reaching for mcp__linear-server__save_issue to "file a
# bug" mid-conversation, duplicating state that belongs in the local tree. The
# prompt says don't; obedience is unreliable. This hook makes it impossible
# outside the one sanctioned path.
#
# Sanctioned path: /ship touches the sentinel immediately before creating the
# tracking ticket. A fresh sentinel (<300s) lets exactly that call through.
# Everything else is denied with a redirect to $TICKETS_DIR.
#
# Block via exit 2 → stderr surfaced back to Claude.

set -u

sentinelDir="${TMPDIR:-/tmp}/claude-linear-guard"
sentinel="${sentinelDir}/ship-ok"

# Fresh sentinel → sanctioned /ship write. Consume it (one-shot) and pass.
if [[ -f "$sentinel" ]]; then
  now=$(date +%s)
  mtime=$(stat -f %m "$sentinel" 2>/dev/null || stat -c %Y "$sentinel" 2>/dev/null || echo 0)
  age=$(( now - mtime ))
  if (( age < 300 )); then
    rm -f "$sentinel"
    exit 0
  fi
  rm -f "$sentinel"
fi

cat >&2 <<'EOF'
🛑 LINEAR ISSUE GUARD — blocked mcp__linear-server__save_issue.

Tickets live in the LOCAL tree ($TICKETS_DIR), not Linear. Linear is write-only;
the only sanctioned write is /ship's §2.5 creating the PR's team-reference ticket.

This block is NOT "skip the ticket." Every PR must carry a Linear ticket so the
team has something to refer to. If you were opening/shipping a PR: STOP, do not
hand-roll `gh pr create`, run /ship — it composes the ticket from real commits+
diff and authorizes this exact write itself. Re-running save_issue raw will just
get blocked again; the fix is the slash command, not a retry.

If this was an ad-hoc mid-work "file a bug" → don't. Write a brief instead:
  $TICKETS_DIR/<area>/<descriptive-slug>.md   (use /scope; slug = descriptor, no IDs)
EOF
exit 2
