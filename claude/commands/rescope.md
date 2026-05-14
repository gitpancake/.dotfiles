---
description: Refine a synced ticket brief locally with user's recommendations. Edits ~/.claude/tickets/<PARENT>/<TICKET>.md only — never writes to Linear.
argument-hint: <LINEAR-ID> [free-text adjustments]
---

# /rescope $ARGUMENTS

`$ARGUMENTS` is `<LINEAR-ID> [optional adjustments]`. First whitespace-separated token =
ticket ID, rest = adjustment text.

Refinement is **local**. This command edits the synced brief on disk; it never touches
Linear. The refined brief reaches Linear later via `/sync-to-linear` (once the work ships)
or is reconciled on the next `/sync-from-linear`.

If only the ticket ID is given, show the brief then **ask** for adjustments and stop.

## 1. Locate + show

Find the brief: `find ~/.claude/tickets -name "<ID>.md" -type f`.
- **Not found** → tell user to run `/sync-from-linear` first, stop.
- **Found** → render the current frontmatter + body verbatim so user sees what changes.

## 2. Decide depth

- **Surface edit** — wording, acceptance-criteria additions, scope clarification. Skip §3.
- **Structural change** — new surface area (new vendor / layer / mechanism). Run §3.

Unsure → treat as structural.

## 3. Codebase exploration (only if structural)

- **Mirror search** — find the structural twin file/feature; cite paths.
- **Surface area** — top ≤8 files to start in, each with a one-line reason.
- **Mechanism honesty** — env vars, vendor accounts, infra prereqs.
- Vendor work → search OpenViking first (`mcp__openviking__search resources/<org>/<vendor>`);
  cite source files or note "no docs indexed."
- For deeper stress-testing against the project's domain model, hand off to the
  `grill-with-docs` skill.

Never invent paths/symbols/env vars. "TBD — needs investigation" beats a guess.

## 4. Compose the refined brief

Rewrite the `## Context` and `## Acceptance criteria` sections of the brief. If structural,
add or update a `## Surface area` section (Mirror / Files to start in / Gotchas). **Preserve
`## Local notes` and everything below it verbatim** — that's lane/agent scratch.

Apply your org's risk callouts where they apply — see `~/.claude/org/<org>/preamble.md` for the
per-org checklist (LLM-cache thresholds, error-budget gates, infra-pairing rules, the project
test command, vendor-proxy routing). Org-specific specifics live in that gitignored file.

## 5. Show the diff. Stop.

```
[<ID>] <current title>
            ↓
[<ID>] <new title>            # only if title changed

DIFF:
- <removed line>
+ <added line>
…
```

**Stop.** Wait for "go" or further edits. Don't write yet.

## 6. On "go": write the local brief

Write the refined sections back to `~/.claude/tickets/<PARENT>/<TICKET>.md`. Update the
frontmatter `title:` if it changed. **Do not call any `mcp__linear-server__*` tool** — Linear
is downstream. Return the file path.

## 7. Stop conditions

- After §1 if no adjustments given — ask once, stop.
- After diff in §5 — wait for "go".
- After write in §6 — done. The brief is ready for `wt <ID>` to pick up.
