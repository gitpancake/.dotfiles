# Global Instructions

## Git Workflow for Coding Projects

When working on coding projects:
- **After completing an isolated chunk of work** (feature, bugfix, refactor), automatically commit the changes with a descriptive message
- **DO NOT push commits automatically** - only commit locally to preserve work and create logical checkpoints
- **Only push when explicitly requested** by the user (e.g., "push", "push to upstream", "deploy")

This allows for incremental progress tracking without premature upstream changes.

## Project Documentation Maintenance

When working in a git repository or code project, keep the project's documentation in sync with changes:

### After each chunk of work
- **Update the project-level `CLAUDE.md`** (create one if it doesn't exist) with any new conventions, architecture decisions, setup steps, gotchas, or non-obvious context discovered during the work. This is the primary place for preserving session-to-session project knowledge.
- **Update `README.md`** if the changes affect user-facing behavior, setup instructions, API surface, or project structure. Skip this for purely internal refactors or minor fixes.

### What to capture in project CLAUDE.md
- Build/test/lint commands and workflows
- Architecture decisions and rationale
- Code conventions and patterns specific to the project
- Known gotchas, workarounds, or non-obvious behaviors
- Dependency or environment requirements

### Guidelines
- Keep updates concise and incremental — add what's new, don't rewrite the whole file each time.
- Only update docs for the project you're actively working in, not unrelated repos.
- Treat this the same as committing code — it's part of completing a chunk of work, not a separate task.

## OpenViking — cross-project knowledge base

OpenViking is a persistent vector-indexed knowledge base (MCP). Its purpose is storing knowledge that **spans projects or lives outside any single repo** — external API docs, cross-project architecture decisions, research findings, and reference material.

**OpenViking is NOT for:** per-project context (use project CLAUDE.md), work summaries (use git), user preferences (use auto-memory), or anything derivable from the current codebase.

### MANDATORY: Check OV before fetching external docs

**Before using `WebFetch`, `WebSearch`, or `context7` to look up API documentation, ALWAYS `find` or `search` OpenViking first.** Henry has indexed key API docs there — re-fetching wastes time and context. If OV has it, use it. If OV doesn't have it and you fetch it externally, store it in OV with `add_resource` for next time.

This applies to any external API, SDK, or service documentation — not just the ones listed below.

### Known resource index

These are currently stored in OV. Check here first — don't re-fetch:

| Topic | OV path |
|-------|---------|
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

This table may become stale. When in doubt, run `ls` on the relevant `resources/` path.

### When to READ from OpenViking

Beyond the mandatory doc-check above, also search OV when:
- **The user asks about cross-project patterns** or prior decisions that aren't in the current repo
- **Starting work that touches multiple projects** — check for stored architecture decisions
- **The user references a service, API, or concept by name** — quick `find` costs nothing

Do NOT search OV for routine coding tasks, UI changes, or work scoped entirely to the current repo.

### When to WRITE to OpenViking

Store content in OV when:
- **You fetch external API docs or reference material** that would be useful in future sessions — store the doc with `add_resource`
- **A cross-project architectural decision is made** that affects multiple repos (e.g., shared auth strategy, deployment patterns)
- **The user explicitly asks** to store something for later reference

Do NOT store: work summaries (git log does this), per-project conventions (CLAUDE.md does this), or ephemeral debugging context.

### Tool quick reference
| Tool | Use when |
|------|----------|
| `search` | Broad/natural language queries ("OpenSea NFT endpoints") |
| `find` | You know roughly what you're looking for ("gondi sdk") |
| `read_content` / `overview` / `abstract` | Reading stored content at different detail levels |
| `add_resource` | Ingesting URLs, docs, or text — use descriptive `reason` fields |
| `ls` / `tree` | Browsing what's stored |
| `rm` | Cleaning up outdated or incorrect entries |

### Hygiene
- When reading an OV entry that's outdated, update or remove it
- Organize resources under descriptive directory names (e.g., `resources/opensea-api/`, not `resources/Document_1/`)
- Prefer fewer, higher-quality entries over many low-value ones
