---
name: to-issues
description: 'Plan/PRD/spec → tracer-bullet vertical tickets in Linear. Trigger: convert plan/create tickets/break down work.'
---

# To Issues

Break a plan into independently-grabbable tickets using vertical slices (tracer bullets),
written to Linear (the source of truth — global CLAUDE.md §Ticket Lifecycle) via the
`linear` skill.

This is the *decomposition* job: take a plan that already exists (in conversation, or a
written brief) and split it into sibling slice tickets. It is distinct from `/scope`, which
engineers a single brief — or a whole project-epic — from free text. If the work is one
sequenced epic, use `/scope`'s epic mode instead; `to-issues` produces a flat set of sibling
issues on one team.

## Process

### 1. Gather context

Work from whatever plan is already in the conversation context. If the user passes a ticket
reference (a Linear id or project name) as an argument, fetch its full description first via
`linear-gql.py`.

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
fire-and-forget `/pickup <id>` lane; a HITL slice is worked interactively.

### 4. Confirm the breakdown

Present the proposed breakdown as a numbered list — per slice: **Title**
(`Feature:`/`Fix:`/... prefix, action-oriented), **Team** (per global CLAUDE.md §Linear
teams), **Type** (HITL/AFK), **Blocked by**. Flag anything you're genuinely unsure about
(granularity, dependency order, team) with your recommendation. Wait for approval before
writing.

### 5. Create the issues in Linear

For each approved slice, `issueCreate` via `linear-gql.py` (bodies through
`--variables-file`, verify `success: true`). Create in dependency order (blockers first) so
blocking relations can reference real issue UUIDs, then wire each "Blocked by" edge with
`issueRelationCreate` (`type: blocks`).

Body sections: `## Requirement`, `## Context` (references the source plan it was decomposed
from), `## Acceptance criteria` (end-to-end behaviour, not layer-by-layer implementation;
avoid file paths / code snippets except a snippet that encodes a decision more precisely
than prose), `## Out of scope` (name the sibling slices that cover adjacent work). The
blocking relations carry dependency — no prose "Blocked by" section needed.

Do not modify the source plan or any parent ticket. Report the created ids + URLs.
