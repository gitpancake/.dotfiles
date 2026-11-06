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
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/_guard.sh"

check_prod_db() {
  guard_is_bash || return 0
  local cmd=$GUARD_CMD

  case "$cmd" in
    *FIREBASE_PRIVATE_KEY*|*FIREBASE_CLIENT_EMAIL*|*credential.cert*)
      guard_ask "🔐 Gate 1 (prod-firestore skill): this uses prod service-account WRITE credentials, not read-only ADC. Approve per-use only — approval never carries over." ;;
  esac

  case "$cmd" in
    *"vercel env pull"*)
      guard_ask "🔐 This writes prod credentials back to disk. The local prod env files were deleted 2026-08-08 on purpose (prod-firestore SKILL.md:45-48). Confirm you want them back." ;;
  esac

  case "$cmd" in
    *"gcloud firestore import"*|*"gcloud firestore export"*)
      guard_ask "🔥 gcloud firestore import/export against production. Import overwrites every document whose ID exists in the export (docs/security/runbooks/firestore-restore.md:36). Confirm containment is in place." ;;
  esac

  case "$cmd" in
    *agent-database-production*) ;;
    *) return 0 ;;
  esac

  # `.add(` is scoped to a collection ref: bare, it fires on every Set.add in a read-only script.
  local writePattern='\.set\(|\.update\(|\.delete\(|\.create\(|collection\([^)]*\)\.add\(|runTransaction|bulkWriter|batch\(\)|\.commit\(\)|recursiveDelete'
  local token path
  for token in $cmd; do
    case "$token" in
      *.ts|*.js|*.mjs|*.cjs) ;;
      *) continue ;;
    esac
    path="$token"
    [[ "$path" != /* ]] && path="$GUARD_CWD/$path"
    [[ -f "$path" ]] || continue
    if grep -Eq "$writePattern" "$path" 2>/dev/null; then
      guard_ask "🔥 Gate 2 (prod-firestore skill): ${token} contains write calls and targets agent-database-production. State the collection, the documents, the exact field changes, and how to reverse it before approving."
    fi
  done

  if grep -Eq "$writePattern" <<<"$cmd"; then
    guard_ask "🔥 Gate 2 (prod-firestore skill): inline write call against agent-database-production. State the collection, the documents, the exact field changes, and how to reverse it before approving."
  fi
}

[[ "${BASH_SOURCE[0]}" == "$0" ]] && guard_main check_prod_db
