---
description: Turn a free-text problem into a Linear ticket draft, refined to engineering-ready with codebase exploration. Mirrors user's house style.
argument-hint: <free-text problem statement>
---

# /scope $ARGUMENTS

user's standard ask is "scope this out and pop it into a ticket, ready for engineering." That means: a future agent or human should be able to pick this up without redoing the discovery. The ticket carries the surface area, the mirror reference, and the gotchas. Don't draft a ticket that just restates the request — refine it.

If `$ARGUMENTS` is empty, ask for a problem statement and stop.

## 1. Clarify before exploring

If `$ARGUMENTS` is under ~15 words **or** missing any of the below, ask up to 3 questions and stop. Skip questions you can already answer.

- **Who hits this**: customer / Voicebot / AO / engineer?
- **End state in one sentence**.
- **Surface area hint**: workflow / integration vendor / UI / infra / prompt — even rough.

## 2. State check (parallel)

Run in parallel:
- `mcp__linear-server__list_projects` — pick by name match (`some-project`, `project-slug`, `carrier-a-integration`, etc.). Default team **AE / Platform Eng** unless context says otherwise.
- `mcp__linear-server__list_issue_labels` — common example-org labels: `voicebot`, `bug`, `alerts-channel-2`, `feature`, vendor names (`shopify`, `carrier-a`, `teams`, `email-api`, `trigger`), surface (`ui`, `prompt`, `infra`).
- `mcp__linear-server__list_issues` — find a recent well-formed ticket in the picked project to mirror structurally.

If no project is an obvious match, ask **once** before proceeding.

## 3. Codebase exploration — the engineering refinement

This is the part user actually wants. Without this, a ticket is a wishlist; with it, it's pickable.

### 3a. Mirror search (before grep)

Most example-org-agent work is "mirror Slack equivalent for Teams" / "mirror Relay for CarrierB" / "mirror Shopify for the next ERP" shaped. Find the structural twin first.

- Is there an existing feature, integration, workflow, or UI surface that this is shaped like? Name it.
- For each layer the new work touches (workflow / route / model / UI / task / tool definition), name the mirror's entry point file. Path + 1-line reason.
- For vendor work, **search OpenViking first** before web search:
  - `mcp__openviking__search` `resources/example-org/<vendor>/`
  - Cite `source_file § section` for any vendor spec claim, or note "no docs indexed for this vendor — propose adding them."

### 3b. Surface area (grounded grep)

After mirror, ground the proposal in actual files:

- Top **≤8 files** to read first to understand the change surface, each with a one-line reason.
- Imports / callers of the affected types and functions (use grep for the mirror's exported symbols).
- Any project `CLAUDE.md` "Gotchas" section entries that apply — quote them inline in §6's Risk callouts.

### 3c. Mechanism honesty

Sanity-check the mechanism. If it depends on something you haven't confirmed:
- Required env vars / secrets — list and flag any not yet set.
- Required external setup (vendor account, webhook URL, OAuth app) — call out as prerequisites.
- Required infra (new Trigger.dev task, new endpoint, new Firestore collection) — call out as scope, not afterthought.

Never invent file paths, function names, or env vars. If you can't grep it, say "TBD — needs investigation" rather than guessing.

## 4. House-style ticket — sections in order

- **Context** — 2–4 sentences. Why this exists. Quote slack / email / customer / tracing-tool run if available.
- **Acceptance criteria** — bulleted, each independently verifiable.
- **Surface area** *(new — from §3)*:
  - **Mirror**: `<feature/file>` — one-line why it's the structural twin.
  - **Files to start in** (≤8): `path:reason`.
  - **Gotchas inherited from CLAUDE.md**: quote the relevant rules verbatim.
- **Out of scope** — explicit. Better to over-list.
- **Open questions** — split:
  - **Ambiguous**: question + who to ask (Alex / Sam / customer / #eng-chat).
  - **Risky**: blast radius + rollback path.
- **Prerequisites** *(new — from §3c)*: env vars to set, vendor accounts to provision, dashboards to access. None? Say "none."
- **References** — Linear IDs, slack threads, tracing-tool run IDs, PRs, OV citations.

## 5. ExampleCorp-specific risk callouts

Add an explicit risk line if the work touches:
- **Voicebot prompts / context** → "verify llm-vendor 95% cache hit rate after merge."
- **Error handling / Sentry / catch blocks** → "Sentry threshold is 0; do not raise."
- **Function signatures with multiple primitives of the same type** → object-params rule.
- **Trigger.dev tasks** → "verify both `TaskRegistry` and `TASK_ROUTES_ENV` updated; either alone is a silent no-op."
- **Tests** → "use `bun test` (`:vm` flag required in worktrees); failure messages must include human-readable explanation for AO."
- **Vendor integration** → "search OpenViking docs first; cite source files. No direct llm-vendor/llm-observability calls — go through llm-gateway."

## 6. Show the draft. Stop.

Format:

```
Title: <≤80 chars, action-oriented, no fluff>
Team:  AE
Project: <picked>
Labels: <picked>
Mirrored after: <Linear ID of structural twin in same project>

Body:
<sections from §4 + §5>
```

**Stop.** Wait for "go" or edits. Do not create until told.

## 7. On "go": create

`mcp__linear-server__create_issue` with the agreed values. Return the issue URL.

After creation, **stop**. Do not start /ticket-pickup. If user wants the slice plan next, he runs `/ticket-pickup <NEW-ID>` — which now has a head-start because §3 already did the surface-area work.

## Stop conditions

- After clarifying questions in §1 — wait for answers.
- After draft in §6 — wait for "go".
- After create in §7 — done.

Never edit code from this command. Never start scoping a slice plan. The whole point is hand-off readiness.
