# Global Instructions

## Verify Before Acting

Before stating ANYTHING about function signatures, file paths, API shapes, event types, env vars, field names, modules, or library methods — **grep or read the source first.** Training data stale. Code is truth.

When uncertain, in order:
1. Grep/read the source.
2. Re-read the Linear ticket.
3. Re-read the original prompt.
4. Ask. Direct question beats confident wrong answer.

No guesses. No invented names.

## Tone

Direct, concise, opinionated. Match user's energy. No disclaimers, hedging, preamble.

## Subagents & Slash Commands

Subagents and slash commands self-describe via Agent/skills schemas — don't list here. Run `/simplify` at chunk boundaries (orchestrator only, not inside subagents). Org preamble: dispatching subagent in known org's codebase → read `~/.claude/org/<org>/preamble.md`, prepend.

## Ticket Lifecycle

`/sync-from-linear` (batch-pull tickets to `~/.claude/tickets/<PARENT>/<TICKET>.md`) → work locally → `/ship` (PR + review) → `/sync-to-linear` (push completed work back). Linear is a boundary touched twice — no live MCP read/write inside the work loop.

- **Regular ticket** → `wt <TICKET>` (or `/pickup <TICKET> <BASE> [context]` to sync the cockpit to a base branch + fold in extra context first) spawns an autonomous lane that reads the synced brief, plans slices inline, leans on the `grill-with-docs` / `tdd` / `handoff` skills, commits per layer, `/ship` at the end.
- **Epic** → `wt --ralph <EPIC>` runs the Ralph autonomous loop in the lane: one story per fresh-context iteration, memory via git + `progress.txt` + `prd.json`.
- **Fresh idea, no ticket** → `/scope <free text>` engineers a local brief at `~/.claude/tickets/_loose/DRAFT-<N>.md` (no Linear write); `wt DRAFT-<N>` picks it up.

**Autonomous semantics.** `wt` lanes fire-and-forget. A lane stops only on: (1) PR open + review triggered, (2) genuine blocker (ambiguity not in the brief, repeated test failure same root cause, missing credential). Brief missing → lane asks for `/sync-from-linear` first. Slice protocol + parallel-lane gotchas: `~/.dotfiles/CLAUDE.md`.

## Planning — local-first

The source of truth for in-flight work is the local file system: `~/.claude/tickets/<PARENT>/<TICKET>.md` for briefs, handoff docs for session state, `prd.json` for Ralph epics. Linear is downstream — synced in via `/sync-from-linear` (occasional batch), out via `/sync-to-linear` (end of day). Never live-fetch a ticket per pickup; brief missing → run `/sync-from-linear`.

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

`turn-cap-warn.sh` fires tiered `systemMessage` warnings at turns 30/50/75/100+. **Honor them.** Past behavior: user habitually ignores soft warns and rides sessions to 600+ turns, where cache_read on the transcript dominates cost. Be the assertive counterweight.

Preferred response is `/handoff` (capture state to a doc the fresh session reads) then `/clear` — more context-efficient than riding the transcript into compaction.

Required response per tier:

- **Turn 30 reminder** — acknowledge once in next reply ("noting turn 30 — we can `/handoff` + `/clear` after this chunk"), continue.
- **Turn 50 warn** — **stop adding new scope this turn.** Finish the in-flight tool chain, then explicitly ask: "We're at 50 turns. `/handoff` + `/clear` now, or push through?" Do not silently proceed past this prompt without an answer.
- **Turn 75 PAUSE** — finish current tool call, then HALT before any further tool use. Surface to user: "Hit the 75-turn pause. I won't start new tool chains until you `/handoff` + `/clear` or explicitly say continue." Single-tool lookups OK, multi-step work blocked until confirmation. An autonomous lane self-invokes `/handoff` here.
- **Turn 100+** — same as 75 but louder. Refuse multi-step work without explicit "I know, push through" from user.

`/handoff` writes a handoff doc; the fresh session reads it instead of re-briefing from memory. For ticket work the synced brief at `~/.claude/tickets/<PARENT>/<TICKET>.md` is the durable anchor.

## Briefs & PRDs — keep them tight

Synced briefs (`~/.claude/tickets/<PARENT>/<TICKET>.md`) and Ralph PRDs (`prd.json`) are re-read on every lane resume / loop iteration — cost compounds. Keep a brief to context + acceptance criteria; keep `## Local notes` to decisions, not narration. Right-size Ralph stories to one context window each.

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
