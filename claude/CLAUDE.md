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

### When to READ from OpenViking

Search or browse OV when:
- **Referencing an external API or service** that may have been previously indexed (e.g., OpenSea, Gondi, Art Blocks, GCP Pub/Sub)
- **Starting work on a project with known OV entries** — check `resources/<project-name>` for stored architecture context
- **The user asks about cross-project patterns** or prior decisions that aren't in the current repo
- **Before fetching external documentation** — check OV first to avoid re-fetching what's already stored

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
