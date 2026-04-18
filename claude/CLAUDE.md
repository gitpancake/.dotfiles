# Global Instructions

## Tone
- Direct, concise, opinionated. Match the user's energy.
- No disclaimers, hedging, or unnecessary preamble.

## Agent Commands

Specialized agents available as slash commands. Use the right agent for the job:

- `/backend` — TypeScript services, event-driven, APIs, RabbitMQ, life-os engines
- `/frontend` — Next.js, React, Tailwind, PWA, design systems
- `/database` — PostgreSQL, Drizzle ORM, schema design, migrations, queries
- `/platform` — Docker, Railway, CI/CD, monitoring, Grafana
- `/fullstack` — End-to-end features spanning backend, DB, API, and frontend
- `/deploy` — Pre-deploy checklist: tests, build, branch verify, ship

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

## Git Workflow

- **Feature branches**: all work on `feature/`, `fix/`, or `refactor/` branches. Main is always deployable.
- **Auto-commit** after each isolated chunk (feature, bugfix, refactor). Separate commits for schema, backend, frontend.
- **Never push** unless explicitly asked ("push", "push to upstream", "deploy").
- **PR creation**: short title (<70 chars), summary + test plan in body. One PR per feature.
- **Merging**: squash merge for clean main history. Delete feature branch after merge.
- **Small projects exception**: solo projects < 1 week old can commit to main directly. Switch to branches once a bad commit would cost >10 minutes to fix.

## Parallel Work (Worktree Agents)

For independent tasks, spawn agents with `isolation: "worktree"` so each runs on its own branch in an isolated checkout. When done, each returns a branch + path; review and merge the ones worth keeping.

- **Good fits**: A/B implementations of the same feature, exploratory refactors, independent bug fixes across unrelated modules, risky experiments.
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

### Known resource index

| Topic | OV path |
|-------|---------|
| Coding practices | `resources/agents/coding-practices` |
| Code structure reference | `resources/agents/code-structure-reference` |
| Frontend architecture reference | `resources/agents/frontend-architecture-reference` |
| Gmail API | `resources/life-os/external-apis/gmail-api` |
| Google Calendar API | `resources/life-os/external-apis/google-calendar-api` |
| GCP Pub/Sub | `resources/life-os/external-apis/gcp-pubsub` |
| Open-Meteo | `resources/life-os/external-apis/open-meteo` |
| Anthropic Claude API | `resources/life-os/external-apis/anthropic-claude-api` |
| Anthropic Models | `resources/life-os/external-apis/anthropic-models` |
| football-data.org v4 | `resources/life-os/external-apis/football-data-v4` |
| Neynar / Farcaster API | `resources/life-os/external-apis/farcaster-neynar-api` |
| Farcaster Hub (direct) | `resources/farcaster-hub-direct-casting` |
| RS3 Hiscores / CML | `resources/rs3-hiscores-api` |
| GCP Pub/Sub infra | `resources/life-os/gcp-pubsub` |
| UI design system | `resources/life-os/ui-design-system` |
| OpenSea API | `resources/opensea-api` |
| Art Blocks API | `resources/art-blocks-api` |
| Gondi SDK / docs | `resources/gondi` |
| Raster.art | `resources/raster-art-research` |

Table may be stale — run `ls` on the relevant `resources/` path when in doubt.

### When to READ

Beyond the mandatory doc-check: search OV when the user asks about cross-project patterns, when starting work that touches multiple projects, or when the user references a service/API by name.

### When to WRITE

Store: external API docs fetched during a session, cross-project architectural decisions, anything the user explicitly asks to save.
Don't store: work summaries, per-project conventions, ephemeral debugging context.

### Hygiene
- Remove or update outdated entries when you encounter them
- Descriptive directory names (`resources/opensea-api/`, not `resources/Document_1/`)
- Fewer high-quality entries over many low-value ones
