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

`/scope` → draft → `/read-ticket` → `/rescope` → `/ticket-pickup` (writes `~/.claude/plans/<ID>.md`, spawns autonomous `wt` lane) → lane runs slice→slice with type-check + test + commit per layer → `/ship`.

**Autonomous semantics.** `wt` and `/ticket-pickup` fire-and-forget. Lane stops only on: (1) PR open + review posted, (2) genuine blocker (ambiguity not in plan, repeated test failure same root cause, missing credential). `wt <slug-or-ID>` auto-resumes from existing plan or invokes `/ticket-pickup`. Slice protocol + parallel-lane gotchas: `~/.dotfiles/CLAUDE.md`.

## Planning — Linear First

Non-trivial tasks: resolve Linear ID, fetch via `mcp__linear-server__get_issue`. MCP unavailable → warn once, proceed on confirmation.

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
- Models: Sonnet default. Haiku for mechanical edits. Opus only for hard architecture.
- Context hygiene: >70% context or >50 tool calls → propose `/clear` + re-brief.

## Session Hygiene — turn-cap protocol

`turn-cap-warn.sh` fires tiered `systemMessage` warnings at turns 30/50/75/100+. **Honor them.** Past behavior: user habitually ignores soft warns and rides sessions to 600+ turns, where cache_read on the transcript dominates cost. Be the assertive counterweight.

Required response per tier:

- **Turn 30 reminder** — acknowledge once in next reply ("noting turn 30 — we can `/clear` after this chunk if it makes sense"), continue.
- **Turn 50 warn** — **stop adding new scope this turn.** Finish the in-flight tool chain, then explicitly ask: "We're at 50 turns. `/clear` + re-brief from `~/.claude/plans/<TICKET>.md` now, or push through?" Do not silently proceed past this prompt without an answer.
- **Turn 75 PAUSE** — finish current tool call, then HALT before any further tool use. Surface to user: "Hit the 75-turn pause. I won't start new tool chains until you `/clear` or explicitly say continue." Single-tool lookups OK, multi-step work blocked until confirmation.
- **Turn 100+** — same as 75 but louder. Refuse multi-step work without explicit "I know, push through" from user.

`/clear` semantics: user runs `/clear`, then pastes a re-brief that names the ticket, the plan path, and where the previous session left off. Plans live at `~/.claude/plans/<TICKET>.md`. Re-brief from the plan, not from memory of the prior turns.

## Plan Size Cap

Plans at `~/.claude/plans/<TICKET>.md` must be ≤200 lines. `plan-lint` FAILS plans over the cap. Reasoning: longer plans cost more on every lane resume and tend to bury the slice protocol. Trim by moving stable detail to subdir notes or the ticket itself; the plan owns the *slice sequence*, not the surrounding context.

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
