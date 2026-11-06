#!/usr/bin/env bash
# PreToolUse hook: deny session-level SET through psql.
#
# Why: on 2026-09-22 a lane prefixed its prod progress queries with
# `SET default_transaction_read_only=on` on the pooled neondb_owner URL.
# Neon's PgBouncer runs in transaction mode and never resets session state, so
# every backend the check touched stayed read-only and was handed to the live
# app. 339 production writes failed over 28 minutes. RCA: ENGH-1725 /
# https://linear.app/cartage/project/rca-2026-09-22-prod-postgres-pool-poisoned-read-only-engh-1664-5274c46c23b0
#
# Denies (not asks — lanes run --dangerously-skip-permissions):
#   - `SET x = ...` / `SET x TO ...` / `SET SESSION x ...` in a psql command
#     (inline -c, heredoc, or a referenced .sql file)
#   - `ALTER ROLE|USER|DATABASE ... SET ...`
#   - `set_config(..., false)` (session scope)
#   - `PGOPTIONS=` on a psql invocation (startup-packet session settings)
#
# Allowed: `SET LOCAL` (transaction-scoped, safe under transaction pooling),
# psql client `\set`, bash `set -a`/`set -u`, and a command whose URL names a
# literal non-pooler Neon host (a direct connection owns its own backend).

set -u

input=$(cat)

[[ "$(jq -r '.tool_name // empty' <<<"$input")" == "Bash" ]] || exit 0

cmd=$(jq -r '.tool_input.command // empty' <<<"$input")
[[ -z "$cmd" ]] && exit 0

grep -Eq '(^|[[:space:];&|(])(psql|pgcli)([[:space:]]|$)' <<<"$cmd" || exit 0

deny() {
  jq -n --arg r "$1" '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: $r
    }
  }'
  exit 0
}

reason="Session-level SET is denied through psql (ENGH-1725, RCA 2026-09-22: a SET default_transaction_read_only=on on the pooled URL leaked to the live app's backends via PgBouncer transaction pooling and failed 339 prod writes). Use plain SELECTs. A read-only role is read-only at the role level and needs no SET. If a setting is truly required, wrap it as SET LOCAL inside an explicit BEGIN/COMMIT."

if grep -Eq '@ep-[a-z0-9-]+\.(c-[0-9]+\.)?[a-z0-9-]+\.aws\.neon\.tech' <<<"$cmd" \
   && ! grep -Eq '@ep-[a-z0-9-]+-pooler\.' <<<"$cmd"; then
  exit 0
fi

sessionSet='(^|[;"'"'"'(]|-c)[[:space:]]*set[[:space:]]+(session[[:space:]]+)?[A-Za-z_][A-Za-z0-9_.]*[[:space:]]*(=|to[[:space:]])'
alterSet='(^|[^A-Za-z0-9_])alter[[:space:]]+(role|user|database)[[:space:]]+.*[[:space:]]set[[:space:]]'
setConfigSession='set_config[[:space:]]*\(.*,[[:space:]]*false[[:space:]]*\)'

text="$cmd"

cwd=$(jq -r '.cwd // empty' <<<"$input")
[[ -z "$cwd" ]] && cwd=$PWD
for token in $cmd; do
  case "$token" in
    *.sql) ;;
    *) continue ;;
  esac
  path="$token"
  [[ "$path" != /* ]] && path="$cwd/$path"
  [[ -f "$path" ]] && text+=$'\n'"$(cat "$path")"
done

if grep -Eiq "$sessionSet" <<<"$text" || grep -Eiq "$alterSet" <<<"$text" || grep -Eiq "$setConfigSession" <<<"$text"; then
  deny "$reason"
fi

if grep -Eq '(^|[[:space:];&(])PGOPTIONS=' <<<"$cmd"; then
  deny "$reason"
fi

exit 0
