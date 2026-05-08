---
description: Scope a Linear ticket into a merge-safe slice plan. Stops before implementation.
argument-hint: <LINEAR-ID>
---

# /ticket-pickup $ARGUMENTS

Produce a scoping doc at `~/.claude/plans/$ARGUMENTS.md`. Do **not** edit any other file. Stop after writing the plan and posting the Linear comment.

If `$ARGUMENTS` is empty, ask for a Linear ID and stop.

## 1. State check (parallel)

Run these in parallel before reading code:

- `mcp__linear-server__get_issue $ARGUMENTS` → full body, comments, status, priority, assignee, labels, parent, sub-issues, attachments.
- For each linked ticket / sub-issue surfaced in the body, fetch it too.
- `gh pr list --search "$ARGUMENTS"` (and `--state all` to catch closed/merged) — is there already work in flight?
- `git log --all --grep="$ARGUMENTS"` — has anyone already started a branch?

**Stop conditions** (report and wait for go):
- Status is in-progress and assignee is not the user.
- An open PR already references this ticket.
- Ticket has a `Blocked` label or unresolved blocker comment.

## 2. Verbatim extraction (no paraphrase)

Paraphrase rewards eloquence; copy-paste rewards understanding.

- **Acceptance criteria** — copy directly from the ticket. If the ticket has none, say so explicitly and propose criteria for user confirmation.
- **Explicitly out of scope** — copy directly. If absent, list what you are *assuming* is out of scope so the user can correct it.
- **Linked tickets / docs** — one-line summary each, with IDs.
- **Recent comments** — last 5 comments verbatim if they shift scope or constraints.

## 3. Mirror search (before grep)

Before searching the codebase blind, look for the analogous feature. Most example-org-agent work is "mirror Slack equivalent for Teams" / "mirror Relay integration for CarrierB" shaped.

- Is there an existing feature this is structurally similar to? Name it.
- For each relevant layer, list the mirror's entry point: workflow, route handler, model, UI component.
- For integration tickets (CarrierA / CarrierB / Relay / CarrierC / CarrierD / CarrierE / Shopify / CarrierF / email-api / etc.), **search OpenViking first** per the example-org org rule:
  - `mcp__openviking__search` `resources/example-org/<vendor>/`
  - Cite `source_file § section` for any spec claim, or say "no docs indexed for this vendor — propose adding them."

## 4. Surface area (grounded grep)

Only after mirror search:

- Top ≤10 files to read first, each with a one-line reason.
- Imports / callers of the affected types and functions.
- Any project `CLAUDE.md` "Gotchas" section entries that apply — quote them.

## 5. Slice plan (trunk-based, merge-safe)

Mirror the TEAM-1450 plan format. Each slice ships to main on its own; the user sees nothing until the final flip.

| # | Slice | User-visible? | Why safe to merge alone |
|---|-------|---------------|-------------------------|
| 1 | … | No | … |
| … | … | … | … |
| N | **Flip** | Yes | One-line registry / endpoint change |

Slices should map cleanly to PR boundaries. If a slice can't merge alone without breaking main or showing half-finished UI, restructure until it can.

## 6. Open questions — split into two lists

Lump diagnostics drive nothing. Split:

**Ambiguous** — concrete question + who to ask:
- Question: …
- Ask: ticket author / Alex / Sam / #eng-chat / customer

**Risky** — blast radius + rollback path:
- What breaks if wrong: …
- Rollback: …

## 7. Estimate

- **Slice count**: 1 / 3 / 5 / 8.
- **Vs prior reference**: "M like AE-XXXX" — pull a prior plan from `~/.claude/plans/` and compare.
- **Top 1–2 unknowns** that would shift it up.

## 8. ExampleCorp-specific checks (if working in example-org-agent)

- Touches **prompts / context / system messages** → flag llm-vendor cache-prefix risk (95% bar).
- Touches **error handling / Sentry / catch blocks** → confirm threshold-0 norm preserved; no catch-and-swallow.
- Touches **function signatures with multiple primitives** → object-params rule.
- Touches **tests** → `bun test` (`:vm` flag required in worktrees), and ensure failures include human-readable explanations for AO.
- Touches **Trigger.dev tasks** → confirm both `TaskRegistry` and `TASK_ROUTES_ENV` are updated (silently no-ops in dev otherwise — known gotcha).

## 9. Branch + worktree

Propose, do not create:

- Branch name: `feature/<ticket-slug>` or `fix/<ticket-slug>` (lowercase, hyphenated, ≤50 chars).
- Worktree path: `<repo>/.claude/worktrees/<ticket-slug>` per example-org worktrees-by-default.
- Trigger command the user can run: `git worktree add <path> -b <branch>`.

## 10. Linear comment

Post via `mcp__linear-server__save_comment`:

> Scoping in progress for $ARGUMENTS. Plan at `~/.claude/plans/$ARGUMENTS.md`. Reviewing with @henry before any code edits.

## Stop condition

After writing `~/.claude/plans/$ARGUMENTS.md` and posting the Linear comment, **stop**. Do not run grep beyond what was needed for sections 3–4. Do not edit any code file. Wait for the user's explicit "go" or follow-up before implementing.
