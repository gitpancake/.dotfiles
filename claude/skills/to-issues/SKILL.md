---
name: to-issues
description: Plan/PRD/spec → tracer-bullet vertical tickets in local tree. Trigger: convert plan/create tickets/break down work.
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

Break the plan into **tracer bullet** tickets. Each ticket is a thin vertical slice that cuts
through ALL integration layers end-to-end, NOT a horizontal slice of one layer.

Slices may be 'HITL' or 'AFK'. HITL slices require human interaction — an architectural
decision, a design review. AFK slices can be implemented and merged without it. Prefer AFK
over HITL where possible. HITL/AFK maps onto how the slice gets picked up: an AFK slice is a
fire-and-forget `wt <slug>` lane; a HITL slice is worked interactively.

<vertical-slice-rules>
- Each slice delivers a narrow but COMPLETE path through every layer (schema, API, UI, tests)
- A completed slice is demoable or verifiable on its own
- Prefer many thin slices over few thick ones
</vertical-slice-rules>

### 4. Quiz the user

Present the proposed breakdown as a numbered list. For each slice, show:

- **Title**: short descriptive name (this becomes the filename slug — kebab-case, no IDs)
- **Area**: which bucket — `integrations` / `platform` / `ops` / `tooling` / `spikes`
- **Type**: HITL / AFK
- **Blocked by**: which other slices (if any) must complete first

Ask the user:

- Does the granularity feel right? (too coarse / too fine)
- Are the dependency relationships correct?
- Should any slices be merged or split further?
- Are the correct slices marked HITL vs AFK?
- Is the area assignment right?

Iterate until the user approves the breakdown.

### 5. Write the tickets to the local tree

For each approved slice, write `$TICKETS_DIR/<area>/<slug>.md` using the frontmatter
from `_TEMPLATE.md` and the body template below. Write in dependency order (blockers first)
so the "Blocked by" field can reference real sibling slugs.

Frontmatter: `status: draft`, `area:` set, `epic:` empty (these are flat siblings, not an
epic folder), `linear:` empty, `created:` current UTC instant as full ISO-8601 with `Z`
suffix (e.g. `2026-05-27T18:13:00Z` — never a bare date; tix needs an instant). Use
`date -u +%Y-%m-%dT%H:%M:%SZ` to get it.

<ticket-body-template>

## Context

2-4 sentences — why this slice exists. Reference the source plan it was decomposed from.

## Acceptance criteria

- Each bullet independently verifiable. Describe end-to-end behaviour, not layer-by-layer
  implementation. Avoid file paths / code snippets — they go stale. Exception: a snippet that
  encodes a decision more precisely than prose (state machine, schema, type shape) — inline
  the decision-rich part only.

## Surface area

- **Files to start in** (≤8): `path — reason`.
- **Gotchas**: quoted project CLAUDE.md rules that apply.

## Out of scope

- Explicit — better to over-list. Name the sibling slices that cover adjacent work.

## Blocked by

- Sibling slug(s) that must land first, or "none — can start immediately".

</ticket-body-template>

Do not modify the source plan or any parent brief.
