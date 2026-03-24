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

## OpenViking — shared context database

You have access to OpenViking, a persistent vector-indexed knowledge base accessible via MCP tools. Use it as your long-term memory across all sessions and projects.

### When starting a session
- **Always `search` OpenViking** at the start of a task for relevant prior context — past decisions, architecture notes, useful references, lessons learned. Do this before diving into code.

### While working
- When you look up external documentation, reference material, or API docs, **`add_resource` them to OpenViking** so they're available in future sessions.
- When you discover important architecture decisions, patterns, or non-obvious project context that would be useful later, store it with `add_resource`.

### When finishing work
- After completing a significant task, **store a brief summary** of what was done, key decisions made, and any gotchas encountered. Use `add_resource` with a text summary.

### Tool usage
- `search` — semantic search, use for broad or natural language queries
- `find` — fast vector lookup, use when you know roughly what you're looking for
- `add_resource` — ingest URLs, docs, or text into the knowledge base
- `read_content` / `overview` / `abstract` — read stored content at different detail levels
- `ls` / `tree` — browse what's stored
- `rm` — clean up outdated or incorrect entries

### Guidelines
- Prefer searching OpenViking before re-reading large codebases or re-fetching documentation you may have already indexed.
- Don't over-index — store things that have lasting value, not ephemeral debugging output.
- Use descriptive `reason` fields when adding resources so future searches surface them well.
