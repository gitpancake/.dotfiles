---
description: Free-text problem → engineered Linear ticket (or project + children). Writes on "go".
argument-hint: <free-text problem statement>
---

# /scope $ARGUMENTS

User's standard ask: "scope this out, ready for engineering." Output is a **Linear issue**
(or, for an epic, a **Linear project + child issues**) whose description a `wt` lane can pick
up without redoing discovery — it carries the surface area, the mirror reference, the
gotchas. Refine the request, don't restate it.

Linear is the source of truth (global CLAUDE.md §Ticket Lifecycle); write via the `linear`
skill (`linear-gql.py`). This command writes to Linear only — plus the one `CONTEXT.md`
docs-commit in §7. Lanes get the brief via `linear-brief.sh` materialization at `/pickup`
time, not from anything /scope leaves on disk.

If `$ARGUMENTS` is empty, infer the problem from conversation context — what was just
discussed, debugged, or decided. Summarize your interpretation in 1–2 sentences and proceed.
No relevant context either → ask for a problem statement and stop.

## 1. Clarify before exploring — grill cadence

If `$ARGUMENTS` is under ~15 words **or** missing any of the below, grill.

**Engine: the `grill-with-docs` skill is /scope's interview loop.** Invoke it here for the
clarification + glossary pass — it owns Design-it-twice cues, `CONTEXT.md` term-pinning, and
domain-vocab discipline. Lanes do not re-grill: this skill is /scope-owned, not lane-owned,
so the brief that ships into `wt` is already sharp.

**One question at a time. Each Q ships w/ your recommended answer.** User affirms → next Q.
User overrides → record + next. Skip what you can already answer from context.

- **Who hits this**: customer / internal user / engineer?
- **End state** in one sentence.
- **Surface area hint**: workflow / vendor / UI / infra / prompt — even rough.
- **Epic or single ticket?**

Format per Q:
> Q: Who hits this?
> Recommended: internal user (you mentioned ops dashboard). Affirm or override.

Walk decision tree — resolve dependencies one branch at a time. Codebase-answerable Q → grep
instead of asking. Stop when above four resolved + no fuzzy terms remain.

## 2. Codebase exploration — the refinement

This is the part that makes the brief pickable rather than a wishlist.

### 2a. Mirror search (before grep)

A lot of work is "mirror an existing integration for a new vendor" shaped. Find
the structural twin first — name it, and for each layer it touches (workflow / route / model
/ UI / task / tool def) name the mirror's entry-point file, path + one-line reason. Vendor
work → check context7 / official docs for the vendor API; cite the doc section used or
note "no docs found."

### 2b. Surface area (grounded grep)

- Top **≤8 files** to start in, each with a one-line reason.
- Imports / callers of the affected types and functions.
- Project `CLAUDE.md` "Gotchas" entries that apply — quote them verbatim.

### 2c. Glossary check

Scan `CONTEXT.md` (root or per-context via `CONTEXT-MAP.md`) for terms in the request. Term
conflicts with existing definition → call out + resolve before drafting. Fuzzy/overloaded
term ("account" = Customer or User?) → propose canonical, get confirmation, update
`CONTEXT.md` inline. No `CONTEXT.md` yet → create lazily only when first term resolves.
Brief must not ship with terms that contradict glossary.

### 2d. Mechanism honesty

Env vars / secrets, external setup (vendor account, webhook, OAuth app), new infra (background
task, endpoint, collection) — list as prerequisites, flag anything unconfirmed. Never invent
paths, symbols, or env vars. "TBD — needs investigation" beats a guess.

### 2e. Design it twice (POSD §11) — only for structural choices

If the brief introduces a structural decision (new data model, new routing-key shape, new
service boundary, vendor adapter, error-propagation strategy) — sketch ≥2 alternatives before
writing the brief. Two bullets each: shape, cost, what it makes easy/hard. Pick one and say
why. **Even when the answer feels obvious, force a second sketch.** First idea is rarely best
for hard problems.

For reversibility (PP §14): if the chosen approach is hard to back out of (DB column we'd
have to migrate off, vendor we'd have to swap, public type shape), add a `## Reversibility`
section. State: what locks us in, what would force a change, rough escape cost. If the choice
deserves an ADR (hard to reverse + surprising + a real trade-off), say so — `/grill-with-docs`
will offer to write it.

Routine choices (which existing helper to call, which existing table to extend) — skip §2e.
Reserve for decisions that survive past the PR.

Apply the org's risk callouts where they fit — `~/.claude/org/<org>/preamble.md`.

## 3. Name it — title, team, shape

- **Title** — `Feature:`/`Fix:`/`Improvement:`/`Refactor:` prefix, action-oriented, derived
  from the end state. Linear adds its own id — never bake one into the title.
- **Team** — per global CLAUDE.md §Linear teams: engineering work → **ENGH**; ops → **AO**;
  agent-behavior/config → **AOA**. Ask only if genuinely ambiguous.
- **Shape** — single issue or epic (project + children), from §1.

Branch/lane slugs derive from the title at `/pickup` time (slug rule: global CLAUDE.md) —
/scope doesn't mint filenames.

## 4. Brief — house style

**Single issue** — description sections, in order:

- `## Requirement` — what's needed, one short paragraph.
- `## Context` — the refined problem: mirror reference, decisions from the grill, gotchas
  quoted from project CLAUDE.md.
- `## Surface area` — mirror / ≤8 starting files with one-line reasons / prerequisites +
  unconfirmed mechanisms from §2d.
- `## Acceptance criteria` — checkboxes, each a testable outcome.
- `## Out of scope` — what this deliberately doesn't touch.
- `## Reversibility` — only when §2e produced one.

**Epic** — a Linear **project** plus one child issue per story:

- Project description follows the spec template: problem → before/after → north star →
  design decisions → execution order (phases, issue-linked) → acceptance criteria →
  hazards → reversibility → appendix (story table + working docs). Exemplars:
  script-retirement `04c92e7d0001`, off-git `c9bdadb3cdfc`.
- Children carry the deep per-story detail (same section shape as a single issue), sized to
  one context window each.
- **Blocking relations ARE the dependency DAG** — `issueRelationCreate` per `needs` edge.
  `/epic` reads them to pick the next story, so they must be complete before any lane spawns.

## 5. Show the draft. Stop.

Render the full draft(s) — title, team, description(s), and for an epic the story list +
DAG. **Stop.** Wait for "go" or edits. Do not write yet.

## 6. On "go": write to Linear

Via the `linear` skill: `issueCreate` (single), or `projectCreate` + `issueCreate` per child
+ `issueRelationCreate` per DAG edge (epic). Set state Backlog, assignee the user, labels
per repo conventions. Bodies via `--variables-file` — never echo markdown through the shell.
Verify `success: true` on every mutation and re-read the project/issue after save (Linear
silently drops some markdown — tables/checkboxes — on bad input). Return:

> `<TEAM-123>` created. Run `/pickup <TEAM-123> <base>` to start a lane.

For an epic:

> Project `<name>` + `<N>` children created. Run `/epic <project> <base>` to review
> story order and spawn the first child lane.

## 7. Commit the glossary edit — if §2c touched `CONTEXT.md`

`CONTEXT.md` is a **project-repo file** — left uncommitted in the cockpit it orphans (lanes
branch off `origin/main` and never see it) and stalls every `wt`/`/pickup` fast-forward.
In the **project repo**, if §2c changed `CONTEXT.md`:

```bash
git -C "$REPO" diff --quiet -- CONTEXT.md || \
  { git -C "$REPO" add CONTEXT.md; \
    git -C "$REPO" commit -q -m "docs: pin <terms> in CONTEXT.md glossary"; }
```

- Stage **`CONTEXT.md` only** — never `git add -A`/`.`; the cockpit may hold unrelated dirty work.
- This is the one project-repo write `/scope` makes (docs-only). Commit only; **never push**.
- No `CONTEXT.md` change this run → skip silently.

## Stop conditions

- After §1 clarifying questions — wait for answers.
- After §5 draft — wait for "go".
- After §6 write — done. The user runs `/pickup <id>` (or `/epic <project>`) next. The §7
  `CONTEXT.md` docs-commit is the only project-repo write; never edit code from this command.
