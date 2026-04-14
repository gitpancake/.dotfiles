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
Domain-specific coding practices live in OpenViking at `resources/agents/coding-practices` — agents search this on-demand.

## Git Workflow

- **Auto-commit** after completing an isolated chunk of work (feature, bugfix, refactor)
- **Never push** unless explicitly asked ("push", "push to upstream", "deploy")

## Project Documentation Maintenance

After each chunk of work:
- **Update project `CLAUDE.md`** with new conventions, architecture decisions, setup steps, gotchas, or non-obvious context. This is the primary session-to-session knowledge store.
- **Update `README.md`** if changes affect user-facing behavior, setup, API surface, or structure. Skip for internal refactors.

Keep updates concise and incremental. Only update docs for the project you're actively working in.

### Scope: Global vs Project CLAUDE.md
- **Global** (this file): workflow rules, agent coordination, tool usage — applies to all projects.
- **Project**: architecture, gotchas, key patterns, commands, deployment — specific to that repo.
- Project CLAUDE.md files must **never exceed 150 lines**. If approaching the limit, cut content that is derivable from reading the code. Keep only: orientation, gotchas that waste hours, patterns you must follow, checklists for adding new things.

## OpenViking — cross-project knowledge base

Persistent vector-indexed knowledge base (MCP) for knowledge that **spans projects or lives outside any single repo** — external API docs, cross-project decisions, research, reference material, agent domain knowledge.

**Not for:** per-project context (CLAUDE.md), work summaries (git), user preferences (auto-memory), anything derivable from code.

### MANDATORY: Check OV before fetching external docs

**Before `WebFetch`, `WebSearch`, or `context7` for API docs, ALWAYS `find`/`search` OpenViking first.** Re-fetching wastes time and context. If OV has it, use it. If not and you fetch externally, store it with `add_resource` for next time.

### Known resource index

| Topic | OV path |
|-------|---------|
| Coding practices | `resources/agents/coding-practices` |
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
