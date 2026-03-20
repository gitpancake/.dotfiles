# Global Instructions

## Git Workflow for Coding Projects

When working on coding projects:
- **After completing an isolated chunk of work** (feature, bugfix, refactor), automatically commit the changes with a descriptive message
- **DO NOT push commits automatically** - only commit locally to preserve work and create logical checkpoints
- **Only push when explicitly requested** by the user (e.g., "push", "push to upstream", "deploy")

This allows for incremental progress tracking without premature upstream changes.

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
