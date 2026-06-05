---
description: Turn a free-text request into a local ticket brief. Writes only after "go".
argument-hint: <free-text problem statement>
---

# /scope $ARGUMENTS

Create a pickable local brief under `${PI_TICKETS_DIR:-$HOME/.pi/tickets}`. Do not edit product code. The brief is the ticket.

## 1. Clarify

If `$ARGUMENTS` is empty, infer from recent conversation. If still unclear, ask for the problem statement and stop.

If the request lacks any of these, ask one question at a time, each with your recommended answer:

- Who hits this: customer, internal user, engineer?
- End state in one sentence.
- Surface area hint: workflow, vendor, UI, infra, prompt, etc.
- Shape: single ticket or epic?

If the `grill-with-docs` skill is available and the problem is fuzzy or structural, load it and use its interview discipline.

## 2. Explore before drafting

Call `scope_ticket` with `action: "inspect"` first when available. It returns the local ticket root, areas, templates, and contract summary without spending context manually reading ticket README/template files. Fall back to reading `$TICKETS_DIR/README.md` and templates only if the tool is unavailable or errors.

Read project `AGENTS.md` / `CLAUDE.md` first and translate any harness-specific instructions to Pi-native tools.

Ground the brief with source inspection:

- Find the closest existing mirror implementation before broad grep.
- Name up to 8 starting files, each with a one-line reason.
- Find callers/imports of affected symbols.
- Quote applicable project gotchas from `AGENTS.md` / `CLAUDE.md`.
- Check `CONTEXT.md` / glossary docs when domain terms are ambiguous.
- List env vars, secrets, external setup, infra, and unknown prerequisites honestly. Never invent paths, symbols, env vars, or API names.

For structural choices, sketch two alternatives with tradeoffs, choose one, and state why. Add reversibility notes if the choice creates lock-in.

## 3. Name it

- Slug: kebab-case, descriptive, <=40 chars, no issue/PR numbers.
- Area: pick an existing `$TICKETS_DIR` bucket if present; otherwise use a sensible bucket like `platform`, `integrations`, `ops`, `tooling`, or `spikes`.
- Single ticket path: `$TICKETS_DIR/<area>/<slug>.md`.
- Epic path: `$TICKETS_DIR/<area>/<epic-slug>/_epic.md` plus ordered child briefs `NN-<child-slug>.md`.

## 4. Draft

Use templates when present:

- `$TICKETS_DIR/_TEMPLATE.md`
- `$TICKETS_DIR/_EPIC-TEMPLATE.md`
- `$TICKETS_DIR/_CHILD-TEMPLATE.md`

Set `created` using `date -u +%Y-%m-%dT%H:%M:%SZ`. Set `status: draft`. Leave external tracker fields blank unless already known.

A good brief includes:

- Problem / end state
- Acceptance criteria
- Starting files
- Relevant mirrors
- Constraints / gotchas
- Test plan
- Prereqs / unknowns
- Local notes for decisions made during scoping

## 5. Stop for approval

Render the full target path(s) and brief content. Stop. Wait for `go` or edits.

## 6. On `go`

Use `scope_ticket` with `action: "write"` when available to create the approved markdown brief; it validates the slug/area, creates parent dirs, and refuses overwrite. Fall back to `write` only if the tool is unavailable or errors. Then report:

`Brief at <path>. Run /pickup <slug> . to continue in Pi.`

Stop. Do not start implementation from `/scope` unless the user explicitly asks.
