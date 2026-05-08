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
- `/scope <free text>` — turn a free-text problem into a Linear ticket draft. Crawls codebase (mirror search, surface area, gotchas, prereqs). Stops before creating; "go" → creates.
- `/read-ticket <ID>` — fetch a Linear ticket and render it in the terminal. Pure read, no edits.
- `/rescope <ID> [adjustments]` — apply user's recommendations to an existing ticket; shows diff, stops, "go" → updates.
- `/ticket-pickup <ID>` — scope an existing Linear ticket into a slice plan, post Linear comment, then spawn a worktree lane via `wt`. Stops before implementation; the spawned lane waits for "go".
- `/ship [PR#]` — commit + push + open PR with house-style bullet body, run a full PR review, report findings as a severity table. Idempotent.
- `/linear-review [team]` — audit user's Linear tickets + open PRs, propose state cleanups (merged→Done, dups, stale backlog cancel, forgotten high-prio flag). Read-only by default; mutations on explicit `go`.

## Ticket Lifecycle (user's house workflow)

```
/scope <problem>          → drafts ticket from free text, creates on go
/read-ticket <ID>         → pulls ticket + comments + linked PRs into the terminal
/rescope <ID> <edits>     → applies your recs, diffs, updates Linear on go
/ticket-pickup <ID>       → writes plan to ~/.claude/plans/<ID>.md, comments on Linear,
                            spawns an AUTONOMOUS worktree lane via `wt`
# (the new lane runs end-to-end, no babysitting:)
slice 1 → type-check + test + commit per layer
slice 2 → …
slice N → final flip
/ship                     → opens PR, runs full review
# Stops only when PR is up + review report is back, or on a genuine blocker.
```

**Autonomous semantics.** `wt` and `/ticket-pickup` are one-shot fire-and-forget. The lane never stops between slices to ask "ready for slice N+1?" — it just goes. It stops on:
1. PR open + review report posted (success).
2. Genuine blocker: ambiguity not resolvable from the plan, repeated test failure on the same root cause, missing credential. Reports and stops.

user watches `agent-board.sh`. Red row → look. Otherwise leave it alone.

`wt <slug-or-TICKET-ID>` is the lane primitive. Linear-style IDs (`TEAM-1530`) auto-resume from `~/.claude/plans/<ID>.md` if it exists, otherwise auto-invoke `/ticket-pickup` first. Lane runs `claude --dangerously-skip-permissions` (override with `WT_CLAUDE='claude' wt …`). Default layout = new tmux window; `WT_LAYOUT=pane|session` overrides.

## Slice Protocol — how user actually ships

user's default cadence for non-trivial Linear tickets is trunk-based slices, not one big PR. Match it.

1. **Scope first**: `/ticket-pickup <ID>` writes a plan to `~/.claude/plans/<ID>.md`. Stops. user reviews.
2. **One slice = one PR**: each slice merges to main on its own and leaves main shippable. If a slice can't merge alone, restructure until it can.
3. **Branch shape**: base feature branch `feature/<ticket-slug>`. Per-slice branches off of it (`agent/<slug>` or `henry/<slug>-slice-N`). Final flip slice merges the feature branch to main.
4. **Per-slice handoff**: user signals "slice N merged, next!" — that means: switch to next slice, re-brief from the plan, do not summarize what you just did. The plan in `~/.claude/plans/` is the source of truth, not your turn history.
5. **Commit per layer**: schema → backend → frontend separate commits inside a slice. user squashes on merge.

## Parallel Worktree Lanes

Default: one lane per ticket. Use `wt <slug-or-TICKET-ID>` to spawn. Outputs:
- worktree at `<repo>/.claude/worktrees/agent-<slug>`
- branch `agent/<slug>` off current HEAD
- per-lane port stamped in `.env.local.port` (3100 + lane index)
- `.claude/agent-state` seeded to `IDLE` (visible to `agent-board.sh`)
- new tmux window running `claude`. Linear-style ID auto-invokes `/ticket-pickup <ID>` (or resumes from existing plan).

**Same-repo parallel-lane gotchas** (assume any could bite when 3+ lanes are live in example-org-agent):
- `node_modules` is per-worktree. First action in a fresh worktree is usually `bun install`.
- Dev servers collide on port. Always read `PORT` from `.env.local.port`; never hardcode.
- Trigger.dev local runners across lanes can race the same task queue. Stagger or scope via env.
- `CLAUDE.md` cache + Linear ticket conventions are shared via the worktree's mounted `.git`.
- Tests inside a worktree must be `bun test` (the `:vm` flag is required for isolation).

## Aggregator Status Pane

Pin a tmux pane running `watch -tcn2 ~/.tmux/agent-board.sh`. It reads `<wt>/.claude/agent-state` for every worktree under `~/Documents/code/*/`. States:
- `IDLE` (dim) — agent done, no pending check
- `RUNNING:precheck` (yellow) — background type-check / tests in flight
- `WAITING:<msg>` (red) — agent paused, needs user's input
- `DONE` (green) — last precheck passed
- `FAILED:<step>` (red) — precheck failed; tail `<wt>/.claude/precheck.log`

Any project that wants the green/red signal drops an executable `.claude/precheck.sh`. Keep it fast (type-check, lint) — it forks to background but it's still the signal user watches.

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
