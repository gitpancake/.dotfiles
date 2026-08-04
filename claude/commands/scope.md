---
description: Free-text problem → engineered ticket brief under $TICKETS_DIR. Writes on "go".
argument-hint: <free-text problem statement>
---

# /scope $ARGUMENTS

User's standard ask: "scope this out, ready for engineering." Output is a **local brief** a
`wt` lane can pick up without redoing discovery — it carries the surface area, the mirror
reference, the gotchas. Refine the request, don't restate it.

Contract + templates: `$TICKETS_DIR/README.md` (default `$TICKETS_DIR/<project>/`, set by zsh `chpwd` hook from git repo basename; flat `$TICKETS_DIR/` outside a repo). This command writes only markdown under `$TICKETS_DIR` — the brief *is* the ticket. There is no upstream tracker.

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

## 3. Name it — slug, area, shape

No counter, no `DRAFT-N`. **The filename is the handle.**

- **Slug** — kebab-case, ≤40 chars, derived from the end state. No numbers (slug rule +
  rationale: global CLAUDE.md §Slug rule).
- **Area** — one of the buckets in `$TICKETS_DIR/` (`integrations`, `platform`, `ops`,
  `tooling`, `spikes`). Pick the closest; ask only if genuinely ambiguous.
- **Shape** — single ticket or epic (from §1).

Target path — a ticket lives in its area from creation, born `status: open`:

- **Single ticket** → `$TICKETS_DIR/<area>/<slug>.md`
- **Epic** → `$TICKETS_DIR/<area>/<epic-slug>/_epic.md` (the PRD) plus
  `$TICKETS_DIR/<area>/<epic-slug>/NN-<child-slug>.md` for each sub-issue, `NN` =
  execution order.

Slug and epic-folder name both match `wt`'s resolver, so `wt <slug>` spawns a lane.

## 4. Brief — house style

Copy the templates. Do not freehand the frontmatter.

- Single ticket → `$TICKETS_DIR/_TEMPLATE.md`
- Epic root → `$TICKETS_DIR/_EPIC-TEMPLATE.md`
- Epic child → `$TICKETS_DIR/_CHILD-TEMPLATE.md`

Every ticket uses the same shape, so lanes read it identically. Set `created` from
`date -u +%Y-%m-%dT%H:%M:%SZ` — run the command, never compose the timestamp (no clock;
model-guessed instants have shipped an hour off). One `date -u` call covers the whole batch.
Set `status: open` on every ticket AND every epic child (a missing `status:` renders as a
muted non-ticket in tix until the next sweep). Leave `linear:` empty — legacy breadcrumb.

**For an epic:** `_epic.md` carries the `<!-- epic-stories:start -->` block — the
authoritative ordered story list plus dependency DAG. Each story's `context:` points at its
`NN-<child>.md`. The children carry the deep per-story detail; `_epic.md` carries
context / goal / constraints / story-list. `/epic` reads `_epic.md` to pick the next story
and each child lane opens its `NN-<child>.md` — so the block must be complete and correctly
ordered before any lane spawns.

## 5. Show the draft. Stop.

Render the full brief(s) and the target path(s). **Stop.** Wait for "go" or edits. Do not
write yet.

## 6. On "go": write

`mkdir -p` the parent dir, write the markdown file(s). Return:

> Brief at `$TICKETS_DIR/<area>/<slug>.md`. Run `wt <slug>` to start a lane.

For an epic:

> Epic at `$TICKETS_DIR/<area>/<epic-slug>/`. Run `/epic <epic-slug> <base>` to review
> the story order and spawn the next child lane.

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
- After §6 write — done. the user runs `wt <slug>` (or `/epic <epic-slug>`) next. The §7
  `CONTEXT.md` docs-commit is the only project-repo write; never edit code from this command.
