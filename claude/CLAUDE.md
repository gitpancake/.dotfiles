# Global Instructions

## Verify Before Acting — No Memory, No Guessing

Before stating ANYTHING about: function signatures, file paths, API shapes, event types, env vars, field names, module structure, or library methods — **grep or read the source first.** Training data is stale. Code is truth.

When uncertain, in order:
1. Grep/read the relevant source.
2. Re-read the Linear ticket.
3. Re-read the original prompt.
4. Ask the human. A direct question beats a confident wrong answer.

Do not proceed on a guess. Do not invent plausible-sounding names.

## Tone
- Direct, concise, opinionated. Match the user's energy.
- No disclaimers, hedging, or unnecessary preamble.

## Specialist Subagents

Dispatch via Agent tool (`subagent_type: "<name>"`). Each is Linear-aware.

- `backend` — services, APIs, event-driven code, workers, background jobs
- `frontend` — UI, components, design systems, Paper-to-code (JSX-only)
- `database` — schema design, migrations, query optimization, indexing
- `fullstack` — end-to-end features spanning DB → service → API → UI in one PR
- `platform` — Docker, observability (Prometheus/Loki/Tempo), build tooling
- `infra` — Railway provisioning, deploy troubleshooting, env/domain config
- `deploy` — pre-ship verification: tests, build, lint, diff review, push

The `code-simplifier` plugin reviews diffs automatically — subagents do not need to invoke `/simplify` themselves.

**Org preamble injection**: When dispatching any subagent in a known org's codebase, read `~/.claude/org/<org>/preamble.md` and prepend to the subagent prompt.

## Global Slash Commands

- `/simplify` — scoped review of the current diff for reuse, clarity, efficiency, dead code. Fixes in place.

## Planning — Linear First

For non-trivial tasks:
1. Ask for (or resolve from context) the Linear issue URL or ID.
2. Fetch via `mcp__linear-server__get_issue` for full scope + acceptance criteria.
3. If Linear MCP unavailable, warn once and proceed on user confirmation.

## Session Start

1. Read project CLAUDE.md before writing code. If none, scan repo and create one.
2. Check OV for relevant context (project name, APIs in use).
3. Check `git status` and branch state. Create feature branch for new work.
4. Check `~/.claude/org/` for org folder. If exists, read `context.md` and apply.

## Code Quality

- Guard clauses at top, early return. Happy path shallowest. Max 2 levels deep.
- One task per function. If it parses AND computes AND formats, split it.
- Specific names: `fetchUserProfile` not `getData`, `delayMs` not `delay`. No `tmp`, `data`, `result`.
- Booleans as assertions: `isValid`, `hasChildren`. Ranges: `first`/`last` or `begin`/`end`.
- Complex conditions become named booleans: `const isOwner = req.user.id === doc.ownerId`.
- `const` by default. Declare close to first use.
- Comment the "why" (tradeoffs, edge cases), never the "what."
- Composition over inheritance. Narrow interfaces over full objects.
- Patterns (Factory, Facade, Adapter) only where they simplify.

Search OV `resources/agents/code-structure-reference` for detailed principles.

## Cost Discipline

Tool calls re-read full conversation context at model price. Heavy loops compound fast.

**Batch pattern**: before touching N items, propose: one LLM call produces a plan, then a script executes it. Never run same tool 20+ times in a row — propose batch instead.

**Model selection**: Opus for planning/architecture. Sonnet for coding (default). Haiku for mechanical edits.

**Context hygiene**: At >70% context or >50 tool calls, propose `/clear` + re-brief. Hook at `~/.claude/hooks/tool-loop-warn.sh` warns at 30 same-tool calls or 100 total.

## Git Workflow

- Feature branches: `feature/`, `fix/`, or `refactor/`. Never `user/` prefix. Main always deployable.
- Auto-commit after each isolated chunk. Separate commits for schema, backend, frontend.
- Never push unless explicitly asked.
- PR: short title (<70 chars), summary + test plan in body. One PR per feature.
- Squash merge. Delete feature branch after merge.

## Branch Safety

Worktree by default for non-trivial work. Assume another agent may be active on any branch. Protocol: `~/.claude/worktree-protocol.md`. Cleanup only on user-confirmed PR merge.

## Project Documentation Maintenance

After each chunk: update project `CLAUDE.md` (conventions, decisions, gotchas). Update `README.md` if user-facing behavior changes.

- Global (this file): workflow rules, code quality, tool usage.
- Project: architecture, gotchas, key patterns, commands, deployment.
- Project CLAUDE.md: never exceed 150 lines. Cut anything derivable from code.

## OpenViking — cross-project knowledge base

Vector-indexed MCP for knowledge spanning projects or outside any single repo — external API docs, cross-project decisions, research.

**Not for**: per-project context (CLAUDE.md), work summaries (git), user preferences (auto-memory).

**MANDATORY**: Before `WebFetch`/`WebSearch`/`context7` for API docs, `find`/`search` OV first. If not found, fetch externally and store with `add_resource`.

Use `mcp__openviking__ls` at `resources/` to discover. Use `find`/`search` for keyword queries. Don't assume a path exists — list first.

Namespaces: `resources/agents/`, `resources/<project>/`, `resources/<api-name>/`.

Read: cross-project patterns, service/API references. Write: external API docs, cross-project decisions. Don't store: per-project conventions, ephemeral context.

Hygiene: descriptive dirs, remove stale entries, fewer high-quality entries.
