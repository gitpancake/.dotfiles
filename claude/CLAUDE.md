# Global Instructions

## Verify Before Acting

Before stating ANYTHING about function signatures, file paths, API shapes, event types, env vars, field names, modules, or library methods — **grep or read the source first.** Training data stale. Code is truth.

When uncertain, in order:
1. Grep/read the source.
2. Re-read the ticket brief.
3. Re-read the original prompt.
4. Ask. Direct question beats confident wrong answer.

No guesses. No invented names.

## Tone

Direct, concise, opinionated. Match user's energy. No disclaimers, hedging, preamble.

## Subagents & Slash Commands

Subagents and slash commands self-describe via Agent/skills schemas — don't list here. Run `/simplify` at chunk boundaries (orchestrator only, not inside subagents). Org preamble: dispatching subagent in known org's codebase → read `~/.claude/org/<org>/preamble.md`, prepend.

## Ticket Lifecycle

Tickets live in `~/.claude/tickets/` — the filesystem is the database, there is no external tracker. Contract + templates: `~/.claude/tickets/README.md`. Filename is a descriptive slug; an epic is a folder with an `_epic.md`.

- **Single ticket** → `/scope <free text>` engineers a brief at `~/.claude/tickets/<area>/<slug>.md`; `wt <slug>` (or `/pickup <slug> <BASE> [context]` to sync the cockpit to a base branch + fold in context first) spawns an autonomous lane that reads the brief, plans slices inline, leans on the `grill-with-docs` / `tdd` / `handoff` skills, commits per layer, `/ship` at the end.
- **Epic** → `/scope` engineers a `<area>/<epic-slug>/_epic.md` + `NN-<child>.md` children; `/epic <epic-slug> <BASE> [context]` confirms the story order and spawns `wt --ralph` — the Ralph autonomous loop runs one story per fresh-context iteration, memory via git + `progress.txt` + `prd.json`. `epic-parse.sh` projects `_epic.md` into the lane's `prd.json`; Ralph executes a confirmed list, never decomposes.

**Autonomous semantics.** `wt` lanes fire-and-forget. A lane stops only on: (1) PR open + review triggered, (2) genuine blocker (ambiguity not in the brief, repeated test failure same root cause, missing credential). Brief missing → lane asks user to `/scope` it. Slice protocol + parallel-lane gotchas: `~/.dotfiles/CLAUDE.md`.

## Planning — filesystem is the database

The source of truth for in-flight work is the local file system: `~/.claude/tickets/` for briefs (contract: its `README.md`), handoff docs for session state, `_epic.md` + `epic-parse.sh` for Ralph epics. There is no upstream — no external tracker, no sync. A ticket is a file; an epic is a folder. Brief missing → `/scope` it.

## Session Start

1. Read project CLAUDE.md before writing code. None → scan repo, create one.
2. Check OV for relevant context.
3. `git status` + branch state. Feature branch for new work.
4. Check `~/.claude/org/` for org folder. Apply `context.md` if exists.

## Code Quality

- Guard clauses, early return. Happy path shallowest. Max 2 levels deep.
- One task per function. Parses AND computes AND formats → split.
- Specific names: `fetchUserProfile` not `getData`. No `tmp`/`data`/`result`.
- Booleans as assertions: `isValid`, `hasChildren`. Ranges: `first`/`last`.
- Complex conditions → named booleans.
- `const` by default. Declare close to first use.
- Comment "why" (tradeoffs, edges), never "what."
- Composition over inheritance. Narrow interfaces.

OV `resources/agents/code-structure-reference` for detail.

## Cost Discipline

Tool calls re-read full conversation context. Heavy loops compound.

- Batch pattern: one LLM call → plan, script applies it. Never run same tool 20+ times.
- Models: Opus for everything — the workflow is context-efficient enough that the sonnet-for-execution hack is retired. Haiku only for bulk mechanical edits (20+ identical changes).
- Context hygiene: >70% context or >50 tool calls → `/handoff` + `/clear`.

## Session Hygiene — turn-cap protocol

`turn-cap-warn.sh` hard-halts at turn 30. Soft reminder at 20. Past behavior: user rode sessions to 600+ turns where cache_read on the transcript dominated cost — this is the assertive counterweight.

Companion hook `auto-handoff.sh` writes a mechanical handoff doc to `~/.claude/handoffs/` at turn 30 so `/clear` is always safe — the fresh session reads it back via `/resume`.

Required response:

- **Turn 20 soft** — wrap the in-flight task before turn 30. Don't start new scope.
- **Turn 30 HARD HALT** — hook injects a mandatory directive: your only allowed response that turn is a short message telling the user to `/clear` immediately. **Do not call any tool, do not continue the in-flight task.** Auto-handoff has already captured state. Reply pattern: `Turn N hard-halt. Auto-handoff at <path>. /clear now — fresh session can /resume.` Autonomous lanes obey identically.
- **Past turn 30** — same halt directive re-fires every prompt until /clear. There is no "push through" — the cost curve is now quadratic.

`/handoff` skill produces richer docs when invoked deliberately; the auto doc is the safety net.

## Briefs & PRDs — keep them tight

Briefs (`~/.claude/tickets/<area>/<slug>.md`) and Ralph PRDs (`prd.json`) are re-read on every lane resume / loop iteration — cost compounds. Keep a brief to context + acceptance criteria; keep `## Local notes` to decisions, not narration. Right-size Ralph stories to one context window each.

## Git Workflow

- Branches: `feature/`, `fix/`, `refactor/`. Never `user/`. Main always deployable.
- Auto-commit per isolated chunk. Separate commits: schema, backend, frontend.
- Never push unless asked. PR title <70 chars. Squash merge.
- Worktree default for non-trivial. Cleanup only on user-confirmed PR merge.

## Project CLAUDE.md

After each chunk: update project `CLAUDE.md` (conventions, decisions, gotchas). Update `README.md` if user-facing behavior changes. Project CLAUDE.md ≤150 lines. Cut anything derivable from code.

## OpenViking

Vector-indexed MCP for cross-project knowledge — external API docs, cross-project decisions, research.

**Not for**: per-project context (CLAUDE.md), work summaries (git), user prefs (auto-memory).

**MANDATORY**: Before `WebFetch`/`WebSearch`/`context7` for API docs, `find`/`search` OV first. Not found → fetch externally + `add_resource`.

`mcp__openviking__ls` at `resources/` to discover. `find`/`search` for keyword queries. List before assuming paths.

Namespaces: `resources/agents/`, `resources/<project>/`, `resources/<api-name>/`.
