# Global Pi Instructions

## Operating style

- Be direct, terse, and opinionated.
- Verify before asserting paths, APIs, function signatures, config keys, env vars, event names, modules, or library methods: search/read source first.
- If uncertain: inspect source, reread the prompt, then ask. Do not invent names.
- Prefer small, targeted changes. Keep file paths explicit in updates.

## Pi workflow

- Use Pi's native strengths: context files, skills, prompt templates, sessions/tree/fork, and extensions.
- Pi user config is source-controlled in `~/.dotfiles/pi/` and symlinked into `~/.pi/agent/`. When creating or editing Pi tooling, write the canonical file under `~/.dotfiles/pi/` first, then run `~/.dotfiles/rewire-symlinks.sh` if a new symlink target is needed.
- Put new Pi extensions in `~/.dotfiles/pi/extensions/`, prompt templates in `~/.dotfiles/pi/prompts/`, skills in `~/.dotfiles/pi/skills/`, themes in `~/.dotfiles/pi/themes/`, helper executables in `~/.dotfiles/pi/bin/`, and global instructions/settings/keybindings in `~/.dotfiles/pi/{AGENTS.md,settings.json,keybindings.json}`.
- Do not create durable custom Pi tooling directly under `~/.pi/agent/`; that tree is the runtime/symlink target. Exceptions are secrets, auth, sessions, npm/git package caches, and other machine-local state, which must stay out of git.
- Project instructions live in `AGENTS.md` or `CLAUDE.md`; read the relevant one before substantive work.
- Use `read` for file contents, `bash` for search/list/test commands, `edit` for precise changes, and `write` for new files or full rewrites.
- For large files, search first and read with `offset`/`limit`; do not full-read big files just to find one symbol.
- Batch exploration and edits. Avoid repeated one-off reads/greps when a single search or script can answer the question.

## Session start

1. Check for project `AGENTS.md` / `CLAUDE.md` and follow it.
2. Check git status and current branch before editing.
3. For new non-trivial work, prefer a feature/fix/refactor branch or existing worktree workflow.
4. If secrets are needed, check `.env.local` then `.env`; never print or hardcode secret values.

## Code quality

- Guard clauses and early returns. Keep nesting shallow.
- One responsibility per function. Split parse/compute/format work.
- Use specific names: `fetchUserProfile`, not `getData`; no vague `tmp`/`data`/`result` unless genuinely generic.
- Boolean names should read as assertions: `isValid`, `hasChildren`.
- Name complex conditions.
- Prefer `const`; declare variables near first use.
- No explanatory code comments unless consumed by tooling or documenting public API. Names and structure should carry intent.
- Composition over inheritance. Narrow interfaces.

## Git and shipping

- Do not push unless asked.
- Commit only when requested or when the local workflow explicitly calls for it.
- Keep schema/backend/frontend/mechanical changes separate when committing.
- Never overwrite user work. If the worktree has unrelated changes, preserve them and ask before touching them.

## Tickets and Claude carry-over

- Local ticket briefs usually live under `$TICKETS_DIR` or `~/.claude/tickets/`; treat that tree as the source of truth when the user says ticket/epic/brief.
- Claude command files are available as Pi prompt templates when configured. They may mention Claude-specific tools; translate intent to Pi tools instead of following impossible mechanics.
- Claude skills are available as Pi skills when configured. Load the matching skill before specialized workflows like TDD, diagnose, handoff, or converting plans to issues.
