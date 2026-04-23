# Global Instructions

## Tone
- Direct, concise, opinionated. Match the user's energy.
- No disclaimers, hedging, or unnecessary preamble.

## Specialist Subagents

Dispatch these via the Agent tool (`subagent_type: "<name>"`) for focused, context-isolated work. Each is Linear-aware: it will try to fetch ticket context from the Linear MCP, and warn once if Linear is unavailable.

- `backend` — services, APIs, event-driven code, workers, background jobs
- `frontend` — UI, components, design systems, Paper-to-code (JSX-only)
- `database` — schema design, migrations, query optimization, indexing
- `fullstack` — end-to-end features spanning DB → service → API → UI in one PR
- `platform` — Docker, observability (Prometheus/Loki/Tempo), build tooling
- `infra` — Railway provisioning, deploy troubleshooting, env/domain config
- `deploy` — pre-ship verification: tests, build, lint, diff review, push

Every subagent ends its workflow by invoking the `/simplify` slash command to review its own diff before declaring done.

## Global Slash Commands

- `/simplify` — scoped review of the current diff for reuse, clarity, efficiency, over-abstraction, dead code. Fixes issues in place.

## Planning — Linear First

Assume the user plans work in Linear. When a task is non-trivial:
1. Ask for (or resolve from context) the Linear issue URL or ID.
2. Fetch it via `mcp__linear-server__get_issue` for full scope + acceptance criteria.
3. If the Linear MCP isn't connected, warn once and proceed on user confirmation — don't silently skip planning context.

## Session Start

When beginning work in any project:
1. Read the project CLAUDE.md before writing code. If none exists, scan the repo and create one.
2. Check OV for relevant context (project name, APIs in use).
3. Check `git status` and branch state. For established projects, create a feature branch if starting new work.

## Code Quality

Apply always when writing, refactoring, or reviewing code:

- Guard clauses at the top, early return. Happy path at shallowest indentation. Max 2 levels deep.
- One task per function. If it parses AND computes AND formats, split it.
- Extract unrelated subproblems into helpers. Main function reads like a plan.
- Specific names: `fetchUserProfile` not `getData`, `delayMs` not `delay`. No `tmp`, `data`, `result`.
- Booleans as assertions: `isValid`, `hasChildren`. Ranges: `first`/`last` or `begin`/`end`.
- Complex conditions become named booleans: `const isOwner = req.user.id === doc.ownerId`.
- `const` by default. Declare close to first use.
- Comment the "why" (tradeoffs, edge cases), never the "what."
- Composition over inheritance. Narrow interfaces — don't pass full objects when 2 fields suffice.
- Patterns (Factory, Facade, Adapter) only where they simplify. A plain function is fine.

Search OV `resources/agents/code-structure-reference` for detailed principles with examples.

## Cost Discipline

Every tool call re-reads the full conversation context at the current model's price. On Opus 1M, a 500k-context turn costs ~25× a Sonnet turn at 100k. Heavy tool loops compound fast.

### Batch pattern (most important)

Before any operation that touches N items (tickets, files, rows, PRs), STOP and propose the batch pattern:
1. One LLM call produces a plan — JSON map, categorization, or action list.
2. A script or targeted API calls execute it without re-invoking the LLM per item.

**If you're about to run the same tool 20+ times in a row, don't.** Propose the batch alternative, get confirmation, then execute. Reserve per-item LLM calls for cases that genuinely need *different* reasoning per item and can't be compressed into one plan.

### Model selection

Match model to task:
- **Opus** — project planning, architecture decisions, breaking down ambiguous work.
- **Sonnet** — coding (default once a plan exists), reviews, most reasoning.
- **Haiku** — mechanical edits, renames, simple greps, trivial changes.

Typical flow: start in Opus to plan, switch to Sonnet once implementing, drop to Haiku for cleanup and mechanical batches. Opus burns ~5× faster than Sonnet — reserve it for when you genuinely need deeper reasoning.

### Context hygiene

At context >70% or tool count >50 in a session, propose `/clear` + re-brief with only essential context. A PostToolUse hook (`~/.claude/hooks/tool-loop-warn.sh`) also emits warnings at 30 same-tool calls or 100 total — treat those as prompts to reassess, not noise.

## Git Workflow

- **Feature branches**: all work on `feature/`, `fix/`, or `refactor/` branches. Main is always deployable. **NEVER use a username prefix (e.g. `user/branch-name`) — always use `feature/`, `fix/`, or `refactor/`.**
- **Auto-commit** after each isolated chunk (feature, bugfix, refactor). Separate commits for schema, backend, frontend.
- **Never push** unless explicitly asked ("push", "push to upstream", "deploy").
- **PR creation**: short title (<70 chars), summary + test plan in body. One PR per feature.
- **Merging**: squash merge for clean main history. Delete feature branch after merge.
- **Small projects exception**: solo projects < 1 week old can commit to main directly. Switch to branches once a bad commit would cost >10 minutes to fix.

## Parallel Work (Worktree Agents)

For independent tasks, spawn agents with `isolation: "worktree"` so each runs on its own branch in an isolated checkout. When done, each returns a branch + path; review and merge the ones worth keeping.

- **Good fits**: one feature split into independent chunks (agent per module/file), or a batch of unrelated small tasks (bug list, cleanups) fanned out at once.
- **Not fits**: anything touching shared runtime state. Worktrees share everything outside `.git` — same DB, same ports, same `node_modules`, same running dev server. Two agents both running `npm install` or hitting port 3000 will collide.
- **Independence check before spawning**: if two agents would edit the same file, it's not parallel work — it's a merge conflict waiting to happen. Split tasks by module/file boundary.
- **Branch naming**: worktree agents branch from current HEAD as `agent/<short-task>`. Squash-merge the winner, discard the rest.

## Project Documentation Maintenance

After each chunk of work:
- **Update project `CLAUDE.md`** with new conventions, architecture decisions, setup steps, gotchas, or non-obvious context.
- **Update `README.md`** if changes affect user-facing behavior, setup, API surface, or structure. Skip for internal refactors.

### Scope: Global vs Project CLAUDE.md
- **Global** (this file): workflow rules, code quality, tool usage — applies to all projects.
- **Project**: architecture, gotchas, key patterns, commands, deployment — specific to that repo.
- Project CLAUDE.md files must **never exceed 150 lines**. If approaching the limit, cut content derivable from code.

## OpenViking — cross-project knowledge base

Persistent vector-indexed knowledge base (MCP) for knowledge that **spans projects or lives outside any single repo** — external API docs, cross-project decisions, research, reference material, agent domain knowledge.

**Not for:** per-project context (CLAUDE.md), work summaries (git), user preferences (auto-memory), anything derivable from code.

### MANDATORY: Check OV before fetching external docs

**Before `WebFetch`, `WebSearch`, or `context7` for API docs, ALWAYS `find`/`search` OpenViking first.** Re-fetching wastes time and context. If OV has it, use it. If not and you fetch externally, store it with `add_resource` for next time.

### Discovering what's in OV

Use `mcp__openviking__ls` at `resources/` to list top-level topics, then drill down. Use `mcp__openviking__find` or `search` for keyword queries across content. Don't assume a path exists — list first.

Common top-level namespaces:
- `resources/agents/` — coding principles, architecture references, cross-project agent knowledge
- `resources/<project>/` — project-scoped external API docs and architecture notes
- `resources/<api-name>/` — standalone external API references

### When to READ

Beyond the mandatory doc-check: search OV when the user asks about cross-project patterns, when starting work that touches multiple projects, or when the user references a service/API by name.

### When to WRITE

Store: external API docs fetched during a session, cross-project architectural decisions, anything the user explicitly asks to save.
Don't store: work summaries, per-project conventions, ephemeral debugging context.

### Hygiene
- Remove or update outdated entries when you encounter them.
- Descriptive directory names (`resources/<service>-api/`, not `resources/Document_1/`).
- Fewer high-quality entries over many low-value ones.
