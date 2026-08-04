---
description: Refine local ticket brief w/ the user's notes. Brief edit only.
argument-hint: <ticket> [free-text adjustments]
---

# /rescope $ARGUMENTS

`$ARGUMENTS` is `<ticket> [optional adjustments]`. First whitespace-separated token = the
ticket (a slug, a Linear id, or an epic folder name), rest = adjustment text.

Refinement is **local**. This command edits the brief on disk — the file *is* the ticket,
there is no upstream to reconcile with.

If only the ticket is given, show the brief then **ask** for adjustments and stop.

## 1. Locate + show

`wt --print-brief <ticket>` → the brief path (the one resolver `wt` uses — do not
re-implement the lookup).
- **Non-zero exit / no path** → tell the user to `/scope` it first, stop.
- **Found** → render the current frontmatter + body verbatim so the user sees what changes.

## 2. Decide depth

- **Surface edit** — wording, acceptance-criteria additions, scope clarification. Skip §3.
- **Structural change** — new surface area (new vendor / layer / mechanism). Run §3.

Unsure → treat as structural.

## 3. Codebase exploration (only if structural)

Run `/scope` §2's exploration pass (mirror search, surface area ≤8 files, mechanism honesty,
vendor docs via context7); deeper stress-testing → the `grill-with-docs` skill. Never invent
paths/symbols/env vars — "TBD — needs investigation" beats a guess.

## 4. Compose the refined brief

Rewrite the `## Context` and `## Acceptance criteria` sections of the brief. If structural,
add or update a `## Surface area` section (Mirror / Files to start in / Gotchas). **Preserve
`## Local notes` and everything below it verbatim** — that's lane/agent scratch.

Apply the org's risk callouts where they apply — `~/.claude/org/<org>/preamble.md`.

## 5. Show the diff. Stop.

Render a `-`/`+` diff of the changed lines (note a title change explicitly). **Stop.** Wait
for "go" or further edits. Don't write yet.

## 6. On "go": write the brief

Write the refined sections back to the brief file. Update the frontmatter `title:` if it
changed. Return the file path.

## 7. Stop conditions

- After §1 if no adjustments given — ask once, stop.
- After diff in §5 — wait for "go".
- After write in §6 — done. The brief is ready for `wt <slug>` to pick up.
