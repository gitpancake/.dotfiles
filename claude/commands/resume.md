---
description: Resume from handoff doc — most recent or matched by description.
argument-hint: "[description of which handoff — omit for the most recent]"
---

# /resume $ARGUMENTS

Pick up where a previous session left off. `/handoff` writes durable docs to
`~/.claude/handoffs/`; this command finds the right one, reads it, and continues the work.

## 1. Find the handoff

```bash
ls -t ~/.claude/handoffs/*.md 2>/dev/null
```

- **No files** → tell the user there are no handoffs and stop.
- **`$ARGUMENTS` empty** → take the most recent (first line of `ls -t`).
- **`$ARGUMENTS` non-empty** → treat it as a description. Match it against the filename
  slugs (case-insensitive substring).
  - Exactly one match → use it.
  - Several matches → list them with dates, ask which, stop.
  - No match → use the most recent and say so explicitly ("no match for `<desc>` —
    resuming the latest instead").

## 2. Read it

Read the chosen file in full. It references other artifacts (briefs, PRDs, commits, PRs)
by path/URL rather than restating them — follow those references as needed before acting.

## 3. Re-orient

Before continuing, verify the world still matches the handoff — it was a snapshot:
- `git status` + branch in any repos the handoff names.
- The brief / ticket / plan it points at still exists and still says what the handoff claims.
- Anything the handoff lists as "done" is actually landed (commit present, PR merged).

Stale handoff (the work moved on, or the named artifact is gone) → surface the gap, don't
blindly execute.

## 4. Continue

Invoke the skills the handoff suggests, then carry on with the work it describes. Give a
two-line orientation ("Resumed from `<file>`. Picking up: `<next step>`.") and proceed —
no need to re-summarise the whole handoff back to the user.

## Stop conditions

- No handoffs, or an ambiguous multi-match description — ask or report, stop.
- Handoff is stale / its anchor artifact is missing — surface, stop for direction.
