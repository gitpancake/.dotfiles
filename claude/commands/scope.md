---
description: Free-text problem → engineered ticket brief under ~/.claude/tickets/. Writes on "go".
argument-hint: <free-text problem statement>
---

# /scope $ARGUMENTS

user's standard ask: "scope this out, ready for engineering." Output is a **local brief** a
`wt` lane can pick up without redoing discovery — it carries the surface area, the mirror
reference, the gotchas. Refine the request, don't restate it.

Contract + templates: `~/.claude/tickets/README.md`. This command writes only markdown under
`~/.claude/tickets/` — the brief *is* the ticket. There is no upstream tracker.

If `$ARGUMENTS` is empty, infer the problem from conversation context — what was just
discussed, debugged, or decided. Summarize your interpretation in 1–2 sentences and proceed.
No relevant context either → ask for a problem statement and stop.

## 1. Clarify before exploring

If `$ARGUMENTS` is under ~15 words **or** missing any of the below, ask up to 3 questions and
stop. Skip what you can already answer.

- **Who hits this**: customer / internal user / engineer?
- **End state** in one sentence.
- **Surface area hint**: workflow / vendor / UI / infra / prompt — even rough.
- **Epic or single ticket?**

## 2. Codebase exploration — the refinement

This is the part that makes the brief pickable rather than a wishlist.

### 2a. Mirror search (before grep)

A lot of work is "mirror an existing integration for a new vendor" shaped. Find
the structural twin first — name it, and for each layer it touches (workflow / route / model
/ UI / task / tool def) name the mirror's entry-point file, path + one-line reason. Vendor
work → search OpenViking first (`mcp__openviking__search resources/<org>/<vendor>`); cite
`source_file § section` or note "no docs indexed."

### 2b. Surface area (grounded grep)

- Top **≤8 files** to start in, each with a one-line reason.
- Imports / callers of the affected types and functions.
- Project `CLAUDE.md` "Gotchas" entries that apply — quote them verbatim.

### 2c. Mechanism honesty

Env vars / secrets, external setup (vendor account, webhook, OAuth app), new infra (background
task, endpoint, collection) — list as prerequisites, flag anything unconfirmed. Never invent
paths, symbols, or env vars. "TBD — needs investigation" beats a guess.

Apply your org's risk callouts where they fit — see `~/.claude/org/<org>/preamble.md` for the
per-org checklist (LLM-cache thresholds, error-budget gates, infra-pairing rules, the project
test command, vendor-proxy routing). Org-specific specifics live in that gitignored file, not here.

## 3. Name it — slug, area, shape

No counter, no `DRAFT-N`. **The filename is the handle.**

- **Slug** — kebab-case, ≤40 chars, descriptive. Derive it from the end state:
  `auth-refactor`, not `draft-7`.
- **Area** — one of the buckets in `~/.claude/tickets/` (`integrations`, `platform`, `ops`,
  `tooling`, `spikes`). Pick the closest; ask only if genuinely ambiguous.
- **Shape** — single ticket or epic (from §1).

Target path — a ticket lives in its area from creation; `status: draft` marks it unrefined
(there is no `_drafts/` staging folder — "draft" is a state, not a location):

- **Single ticket** → `~/.claude/tickets/<area>/<slug>.md`
- **Epic** → `~/.claude/tickets/<area>/<epic-slug>/_epic.md` (the PRD) plus
  `~/.claude/tickets/<area>/<epic-slug>/NN-<child-slug>.md` for each sub-issue, `NN` =
  execution order.

Slug and epic-folder name both match `wt`'s resolver, so `wt <slug>` spawns a lane.

## 4. Brief — house style

Copy the templates. Do not freehand the frontmatter.

- Single ticket → `~/.claude/tickets/_TEMPLATE.md`
- Epic root → `~/.claude/tickets/_EPIC-TEMPLATE.md`
- Epic child → `~/.claude/tickets/_CHILD-TEMPLATE.md`

Every ticket uses the same shape, so lanes read it identically. Set `created` to now,
`status: draft`. Leave `linear:` empty — it's only a breadcrumb on tickets that predate the
local-only move.

**For an epic:** `_epic.md` carries the `<!-- epic-stories:start -->` block — the
authoritative ordered story list plus dependency DAG. Each story's `context:` points at its
`NN-<child>.md`. The children carry the deep per-story detail; `_epic.md` carries
context / goal / constraints / story-list. Ralph reads `_epic.md` to start and opens a child
when it picks that story — so the block must be complete and correctly ordered before any
lane spawns.

## 5. Show the draft. Stop.

Render the full brief(s) and the target path(s). **Stop.** Wait for "go" or edits. Do not
write yet.

## 6. On "go": write

`mkdir -p` the parent dir, write the markdown file(s). Return:

> Brief at `~/.claude/tickets/<area>/<slug>.md`. Run `wt <slug>` to start a lane.

For an epic:

> Epic at `~/.claude/tickets/<area>/<epic-slug>/`. Run `/epic <epic-slug> <base>` to review
> the story order and spawn the Ralph lane.

## Stop conditions

- After §1 clarifying questions — wait for answers.
- After §5 draft — wait for "go".
- After §6 write — done. user runs `wt <slug>` (or `/epic <epic-slug>`) next. Never edit
  code from this command.
