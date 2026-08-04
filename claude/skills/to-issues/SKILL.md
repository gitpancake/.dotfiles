---
name: to-issues
description: 'Plan/PRD/spec → tracer-bullet vertical tickets in local tree. Trigger: convert plan/create tickets/break down work.'
---

# To Issues

Break a plan into independently-grabbable tickets using vertical slices (tracer bullets),
written into the local ticket tree at `$TICKETS_DIR/`.

This is the *decomposition* job: take a plan that already exists (in conversation, or a
written brief) and split it into sibling slice tickets. It is distinct from `/scope`, which
engineers a single brief — or a whole `_epic.md` folder — from free text. If the work is one
sequenced epic, use `/scope`'s epic mode instead; `to-issues` produces a flat set of sibling
tickets in one area.

The contract for what a ticket file looks like is `$TICKETS_DIR/README.md` — read it
before writing. Frontmatter comes from `$TICKETS_DIR/_TEMPLATE.md`; do not freehand it.

## Process

### 1. Gather context

Work from whatever plan is already in the conversation context. If the user passes a brief
reference (a ticket slug or a path under `$TICKETS_DIR/`) as an argument, read its full
body first.

### 2. Explore the codebase (optional)

If you have not already explored the codebase, do so to understand the current state. Ticket
titles and descriptions should use the project's domain vocabulary and respect ADRs in the
area you're touching.

### 3. Draft vertical slices

Break the plan into **tracer bullet** tickets: each a thin vertical slice through ALL
integration layers end-to-end (schema, API, UI, tests) — never a horizontal slice of one
layer. A completed slice is demoable or verifiable on its own; prefer many thin slices
over few thick ones.

Slices may be 'HITL' or 'AFK'. HITL slices require human interaction — an architectural
decision, a design review. AFK slices can be implemented and merged without it. Prefer AFK
over HITL where possible. HITL/AFK maps onto how the slice gets picked up: an AFK slice is a
fire-and-forget `wt <slug>` lane; a HITL slice is worked interactively.

### 4. Confirm the breakdown

Present the proposed breakdown as a numbered list — per slice: **Title** (becomes the
filename slug — kebab-case, no IDs), **Area** bucket, **Type** (HITL/AFK), **Blocked by**.
Flag anything you're genuinely unsure about (granularity, dependency order, area) with your
recommendation. Wait for approval before writing.

### 5. Write the tickets to the local tree

For each approved slice, write `$TICKETS_DIR/<area>/<slug>.md` using the frontmatter
from `_TEMPLATE.md` and the body template below. Write in dependency order (blockers first)
so the "Blocked by" field can reference real sibling slugs.

Frontmatter: `status: open`, `area:` set, `epic:` empty (these are flat siblings, not an
epic folder), `linear:` empty, `created:` the output of `date -u +%Y-%m-%dT%H:%M:%SZ` —
run the command, never compose the timestamp (no clock; model-guessed instants have shipped
an hour off, and tix needs an instant, not a bare date). One `date -u` call covers the
whole batch.

Body: `_TEMPLATE.md`'s sections, with two slice-specific adjustments — `## Context`
references the source plan it was decomposed from; add a `## Blocked by` section listing
the sibling slug(s) that must land first (or "none — can start immediately"). In
`## Acceptance criteria`, describe end-to-end behaviour, not layer-by-layer implementation;
avoid file paths / code snippets except a snippet that encodes a decision more precisely
than prose. In `## Out of scope`, name the sibling slices that cover adjacent work.

Do not modify the source plan or any parent brief.
