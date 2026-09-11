---
description: Refine a Linear ticket's brief w/ the user's notes. Description edit only.
argument-hint: <ticket> [free-text adjustments]
---

# /rescope $ARGUMENTS

`$ARGUMENTS` is `<ticket> [optional adjustments]`. First whitespace-separated token = the
ticket (a Linear id, or the slug of a materialized brief — read its `linear:` frontmatter),
rest = adjustment text.

Refinement happens **in Linear** — the issue description *is* the brief (global CLAUDE.md
§Ticket Lifecycle). Any local materialized file is a cache this command refreshes at the end.

If only the ticket is given, show the brief then **ask** for adjustments and stop.

## 1. Locate + show

Fetch via the `linear` skill: `issue(id:){ id title description state { name } url }`.
- **Not found** → tell the user to `/scope` it first, stop.
- **Found** → render title + description verbatim so the user sees what changes.

## 2. Decide depth

- **Surface edit** — wording, acceptance-criteria additions, scope clarification. Skip §3.
- **Structural change** — new surface area (new vendor / layer / mechanism). Run §3.

Unsure → treat as structural.

## 2.5. Evidence refresh (on request, or when /pickup's staleness check sent you here)

When the user asks to refresh from meetings ("--evidence", "check the calls", or arriving
via /pickup §2.3), pull the delta since the brief was last edited:

```bash
~/.dotfiles/scripts/pocket.py search "<ticket title key terms>" --limit 8
~/.dotfiles/scripts/granola.py notes --since-days <days-since-updatedAt> --limit 20
```

For each relevant hit newer than the issue's `updatedAt`, extract candidate scope changes
and present them /scope §1-style — one per Q, verbatim quote + speaker + recommended
disposition (add to AC / add to Limitations / ignore), affirm or override. Confirmed items
fold into §4's rewrite with inline citations per /scope's provenance rule (`(per Ben, 8/14
call: "…")`; inferred speakers marked `(speaker inferred)`). No relevant hits → say so and
continue with the user's adjustments alone.

## 3. Codebase exploration (only if structural)

Run `/scope` §2's exploration pass (mirror search, surface area ≤8 files, mechanism honesty,
vendor docs via context7) and its §2e design pass — two sketches, pattern-or-none with the
force named, the maintainability gate; deeper stress-testing → the `grill-with-docs` skill. Never invent
paths/symbols/env vars — "TBD — needs investigation" beats a guess.

## 4. Compose the refined brief

Rewrite the `## Context` and `## Acceptance criteria` sections of the description. If
structural, add or update `## Surface area` (Mirror / Files to start in / Gotchas) and
`## Design` (shape, pattern + force, rejected alternative, gate answers — per `/scope` §4).
Apply the org's risk callouts where they apply — `~/.claude/org/<org>/preamble.md`.

## 5. Show the diff. Stop.

Render a `-`/`+` diff of the changed lines (note a title change explicitly). **Stop.** Wait
for "go" or further edits. Don't write yet.

## 6. On "go": write to Linear + refresh the cache

`issueUpdate` with the refined description (and `title` if changed) via the `linear` skill —
body through `--variables-file`, verify `success: true`, re-read to confirm markdown
survived. Then refresh any local materialization:

```bash
old=$(grep -rlE "^linear:[[:space:]]+<ID>" "${TICKETS_DIR:-$HOME/.claude/tickets}" --include='*.md' 2>/dev/null | head -1)
[[ -n "$old" ]] && { rm "$old"; ~/.dotfiles/scripts/linear-brief.sh "<ID>"; }
```

(Preserve any `## Local notes` from the old cache file by re-appending it — that's lane
scratch, not scope.) Return the issue URL.

## 7. Stop conditions

- After §1 if no adjustments given — ask once, stop.
- After diff in §5 — wait for "go".
- After write in §6 — done. The ticket is ready for `/pickup <id>`.
