---
description: Adjust an existing Linear ticket with user's recommendations and update it. Mirrors /scope's house style; codebase exploration only if structural change needed.
argument-hint: <LINEAR-ID> [free-text adjustments]
---

# /rescope $ARGUMENTS

`$ARGUMENTS` is `<LINEAR-ID> [optional adjustments]`. Two-arg parsing: first whitespace-separated token = ticket ID, rest = adjustment text.

If only the ticket ID is given, fetch the ticket then **ask** for adjustments and stop. If both are given, proceed.

## 1. Fetch + show

- `mcp__linear-server__get_issue <ID>` — current full body.
- Render the **current title + body** (verbatim, no paraphrase) so user sees what's about to change.

## 2. Decide depth

Inspect user's adjustments against the ticket. Pick one:

- **Surface edit** — wording, acceptance-criteria additions, label/project change, scope clarification. Skip §3 codebase work.
- **Structural change** — new surface area introduced (new vendor / new layer / new mechanism). Run §3.

If unsure, treat as structural.

## 3. Codebase exploration (only if structural)

Same shape as `/scope` §3:
- **Mirror search** — find the structural twin file/feature; cite paths.
- **Surface area** — top ≤8 files to start in, each with a one-line reason.
- **Mechanism honesty** — env vars, vendor accounts, infra prereqs.
- For vendor work: search OpenViking first (`mcp__openviking__search resources/example-org/<vendor>`); cite source files or note "no docs indexed."

Never invent paths/symbols/env vars. "TBD — needs investigation" beats a guess.

## 4. Compose new ticket — house style

Sections in order (mirror `/scope` §4):
- Context
- Acceptance criteria
- **Surface area** — Mirror, Files to start in (≤8), Gotchas (CLAUDE.md quotes)
- Out of scope
- Open questions — Ambiguous / Risky split
- Prerequisites
- References

Apply `/scope` §5 example-org risk callouts where they apply (Voicebot prompts, Sentry threshold, object-params, Trigger.dev pair, `bun test`, vendor calls through llm-gateway).

## 5. Show the diff. Stop.

Render in this shape:

```
[<ID>] <Old title>
            ↓
[<ID>] <New title>            # only if title changed

DIFF:
- <removed line>
+ <added line>
- <removed section header>
+ <added section header>
…

LABELS: <added, removed>
PROJECT: <old → new>           # only if changed
STATE: <old → new>             # only if changed
```

**Stop.** Wait for "go" or further edits. Don't update yet.

## 6. On "go": update

`mcp__linear-server__update_issue` with the agreed body / title / labels / project / state.

Post a Linear comment summarizing the change in one sentence: "Refined: <one-line summary>." (via `mcp__linear-server__save_comment`).

Return: ticket URL.

## 7. Stop conditions

- After fetch in §1 if no adjustments given — ask once, stop.
- After diff in §5 — wait for "go".
- After update in §6 — done. Do not start `/ticket-pickup`. user runs that next if he wants the slice plan.
