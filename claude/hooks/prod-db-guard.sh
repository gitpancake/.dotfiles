#!/usr/bin/env bash
# PreToolUse hook: force a permission prompt on prod-database write paths.
#
# Why this exists as a hook and not a permission rule: the guardrails for
# agent-database-production live in ~/.claude/skills/prod-firestore/SKILL.md as
# prose ("Gate 1 — write credentials", "Gate 2 — any write", "approval never
# carries over"). Prose is followed, not enforced. Nothing in settings.json
# mentions Firestore, and the dangerous invocation is an ordinary-looking
#   GOOGLE_CLOUD_PROJECT=agent-database-production bun run src/.../_tmpX.ts
# whose writes are inside the .ts file, invisible to a Bash(...) glob.
#
# Contract:
#   - Bash only. Editing a script is fine; RUNNING it is the gate.
#   - Reads stay free, per SKILL.md:12-13 (read-only ADC needs no permission).
#     A prod command is only gated when the script it runs contains a write
#     call, or when the command itself touches write credentials / bulk import.
#   - Gating means permissionDecision:"ask" — a prompt, not a block. The user
#     can still say yes; they just have to say it every time, which is the
#     stated contract.
#
# Unconditional triggers (always ask, read or not):
#   - prod service-account credentials  (Gate 1)
#   - gcloud firestore import/export    (bulk overwrite by document ID)
#   - vercel env pull                   (puts prod write creds back on disk)

set -u

input=$(cat)

[[ "$(jq -r '.tool_name // empty' <<<"$input")" == "Bash" ]] || exit 0

cmd=$(jq -r '.tool_input.command // empty' <<<"$input")
[[ -z "$cmd" ]] && exit 0

ask() {
  jq -n --arg r "$1" '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "ask",
      permissionDecisionReason: $r
    }
  }'
  exit 0
}

# --- Unconditional triggers -------------------------------------------------

case "$cmd" in
  *FIREBASE_PRIVATE_KEY*|*FIREBASE_CLIENT_EMAIL*|*credential.cert*)
    ask "🔐 Gate 1 (prod-firestore skill): this uses prod service-account WRITE credentials, not read-only ADC. Approve per-use only — approval never carries over." ;;
esac

case "$cmd" in
  *"vercel env pull"*)
    ask "🔐 This writes prod credentials back to disk. The local prod env files were deleted 2026-08-08 on purpose (prod-firestore SKILL.md:45-48). Confirm you want them back." ;;
esac

case "$cmd" in
  *"gcloud firestore import"*|*"gcloud firestore export"*)
    ask "🔥 gcloud firestore import/export against production. Import overwrites every document whose ID exists in the export (docs/security/runbooks/firestore-restore.md:36). Confirm containment is in place." ;;
esac

# --- Prod-project commands: ask only if the script writes -------------------

case "$cmd" in
  *agent-database-production*) ;;
  *) exit 0 ;;
esac

# Bare `\.add\(` would fire on every `someSet.add(...)` in a read-only script,
# so it is scoped to a Firestore collection ref. Everything else here is
# write-only vocabulary in practice.
writePattern='\.set\(|\.update\(|\.delete\(|\.create\(|collection\([^)]*\)\.add\(|runTransaction|bulkWriter|batch\(\)|\.commit\(\)|recursiveDelete'

# The command names the script; the writes are inside it. Resolve every
# file-ish token against cwd and scan it.
cwd=$(jq -r '.cwd // empty' <<<"$input")
[[ -z "$cwd" ]] && cwd=$PWD

for token in $cmd; do
  case "$token" in
    *.ts|*.js|*.mjs|*.cjs) ;;
    *) continue ;;
  esac
  path="$token"
  [[ "$path" != /* ]] && path="$cwd/$path"
  [[ -f "$path" ]] || continue
  if grep -Eq "$writePattern" "$path" 2>/dev/null; then
    ask "🔥 Gate 2 (prod-firestore skill): ${token} contains write calls and targets agent-database-production. State the collection, the documents, the exact field changes, and how to reverse it before approving."
  fi
done

# Inline writes (bun -e '...', node -e '...', heredoc) never touch a file.
if grep -Eq "$writePattern" <<<"$cmd"; then
  ask "🔥 Gate 2 (prod-firestore skill): inline write call against agent-database-production. State the collection, the documents, the exact field changes, and how to reverse it before approving."
fi

exit 0
