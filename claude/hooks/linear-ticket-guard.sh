#!/usr/bin/env bash
# PreToolUse hook: block freelance `linear-ticket.py create` calls.
#
# Doctrine: $TICKETS_DIR is the source of truth; Linear is a write-only sink
# touched only by `/ship` (PR's reference ticket) and the `bugfinder` agent
# (one ticket per confirmed bug). Free-form work that calls
# `linear-ticket.py create` directly creates orphan Linear issues with no PR,
# no brief, no local home — exactly the leak this hook closes.
#
# Authorization is by inline env: an approved call site prefixes the command
# with `LINEAR_TICKET_CREATE_OK=1`. Anything else is blocked (exit 2) with a
# corrective message back to Claude.
#
# Scope:
#   - Only Bash tool calls.
#   - Only commands that invoke `linear-ticket.py create` (subcommands like
#     `comment` / `update` pass — those are the agent-comment path and fine).

set -u

input=$(cat)

toolName=$(jq -r '.tool_name // empty' <<<"$input")
[[ "$toolName" != "Bash" ]] && exit 0

cmd=$(jq -r '.tool_input.command // empty' <<<"$input")
[[ -z "$cmd" ]] && exit 0

# Match `linear-ticket.py create` with anything between (path, args) — but
# specifically the `create` subcommand, not `comment`/`update`/`list`.
if ! grep -Eq 'linear-ticket\.py[[:space:]]+(\\?[[:space:]]*\n?)*[^|;&]*\bcreate\b' <<<"$cmd"; then
  # Fallback: simpler check that tolerates line continuations and pipes.
  if ! grep -Eq 'linear-ticket\.py.*\bcreate\b' <<<"$cmd"; then
    exit 0
  fi
fi

# Allow if the call site set the authorization env var inline.
if grep -q 'LINEAR_TICKET_CREATE_OK=1' <<<"$cmd"; then
  exit 0
fi

cat >&2 <<'MSG'
Blocked: `linear-ticket.py create` is not an open call site.

Linear is a write-only sink. Authorized creators:
  - `/ship` — creates the PR's reference ticket
  - `bugfinder` agent — one ticket per confirmed bug

Free-form scope/diagnosis work belongs in `$TICKETS_DIR` (local), not Linear.
If you genuinely need to create a ticket here, prefix the command with
`LINEAR_TICKET_CREATE_OK=1` to acknowledge — but first confirm a local brief
under `$TICKETS_DIR` exists and a PR will follow via `/ship`.
MSG
exit 2
