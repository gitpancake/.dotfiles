---
description: Turn a free-text problem into an engineered local ticket brief under ~/.claude/tickets/. Includes codebase exploration. Writes the markdown on "go" — never touches Linear.
argument-hint: <free-text problem statement>
---

# /scope $ARGUMENTS

user's standard ask: "scope this out, ready for engineering." Output is a **local brief** a
`wt` lane can pick up without redoing discovery — it carries the surface area, the mirror
reference, the gotchas. Refine the request, don't restate it.

**Never touches Linear.** Briefs become Linear tickets later via `/sync-to-linear`, after the
work ships. This command only writes markdown under `~/.claude/tickets/`.

If `$ARGUMENTS` is empty, infer the problem from conversation context — what was just
discussed, debugged, or decided. Summarize your interpretation in 1–2 sentences and proceed.
No relevant context either → ask for a problem statement and stop.

## 1. Clarify before exploring

If `$ARGUMENTS` is under ~15 words **or** missing any of the below, ask up to 3 questions and
stop. Skip what you can already answer.

- **Who hits this**: customer / Voicebot / AO / engineer?
- **End state** in one sentence.
- **Surface area hint**: workflow / vendor / UI / infra / prompt — even rough.
- **Epic or single ticket?**

## 2. Codebase exploration — the refinement

This is the part that makes the brief pickable rather than a wishlist.

### 2a. Mirror search (before grep)

Most example-org-agent work is "mirror Slack for Teams" / "mirror Relay for CarrierB" shaped. Find
the structural twin first — name it, and for each layer it touches (workflow / route / model
/ UI / task / tool def) name the mirror's entry-point file, path + one-line reason. Vendor
work → search OpenViking first (`mcp__openviking__search resources/example-org/<vendor>`); cite
`source_file § section` or note "no docs indexed."

### 2b. Surface area (grounded grep)

- Top **≤8 files** to start in, each with a one-line reason.
- Imports / callers of the affected types and functions.
- Project `CLAUDE.md` "Gotchas" entries that apply — quote them verbatim.

### 2c. Mechanism honesty

Env vars / secrets, external setup (vendor account, webhook, OAuth app), new infra (Trigger.dev
task, endpoint, collection) — list as prerequisites, flag anything unconfirmed. Never invent
paths, symbols, or env vars. "TBD — needs investigation" beats a guess.

Apply example-org risk callouts where they fit: Voicebot prompts → llm-vendor 95% cache bar; error
handling → Sentry threshold 0; multi-primitive signatures → object-params; Trigger.dev →
`TaskRegistry` + `TASK_ROUTES_ENV` pair; tests → `bun test`; vendor calls → through llm-gateway.

## 3. Allocate a draft ID

Scan `~/.claude/tickets/` for `DRAFT-*.md`, take the max N, use `DRAFT-<N+1>`.

- **Single ticket** → `~/.claude/tickets/_loose/DRAFT-<N>.md`.
- **Epic** → `~/.claude/tickets/DRAFT-<N>/DRAFT-<N>.md` (the epic) plus
  `~/.claude/tickets/DRAFT-<N>/DRAFT-<N+k>.md` for each sub-issue, so they nest like synced
  tickets do.

Draft IDs match `wt`'s ticket pattern, so `wt DRAFT-<N>` spawns a lane exactly like a real ID.
When the work ships, `/sync-to-linear` creates the real Linear ticket.

## 4. Brief — house style

Same shape `/sync-from-linear` writes, so lanes read it identically.

```
---
id: DRAFT-7
parent: _loose            # or DRAFT-<N> if this is a sub-issue
title: <≤80 chars, action-oriented, no fluff>
status: Draft
project: <best-guess project slug, or TBD>
labels: [<best-guess labels>]
url:
synced: <ISO-8601 now>
---

## Context
<2–4 sentences — why this exists. Quote slack / email / customer / tracing-tool if available.>

## Acceptance criteria
- <bulleted, each independently verifiable>

## Surface area
- **Mirror**: `<feature/file>` — one-line why it's the structural twin.
- **Files to start in** (≤8): `path:reason`.
- **Gotchas**: quoted CLAUDE.md rules that apply.

## Out of scope
- <explicit — better to over-list>

## Open questions
- **Ambiguous**: <question + who to ask: Alex / Sam / customer / #eng-chat>
- **Risky**: <blast radius + rollback path>

## Prerequisites
<env vars to set, accounts to provision, infra to stand up. None → "none.">

## Local notes
<!-- lane / agent scratch — preserved across any later /sync-from-linear -->
```

## 5. Show the draft. Stop.

Render the full brief(s) and the target path(s). **Stop.** Wait for "go" or edits. Do not
write yet.

## 6. On "go": write

`mkdir -p` the parent dir, write the markdown file(s). Return:

> Brief at `~/.claude/tickets/_loose/DRAFT-7.md`. Run `wt DRAFT-7` to start a lane.

## Stop conditions

- After §1 clarifying questions — wait for answers.
- After §5 draft — wait for "go".
- After §6 write — done. user runs `wt DRAFT-<N>` next. Never edit code from this command.
