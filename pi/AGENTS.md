# Global Pi Instructions

## Operating style

- Be direct, terse, and opinionated.
- Verify before asserting paths, APIs, function signatures, config keys, env vars, event names, modules, or library methods: search/read source first.
- If uncertain: inspect source, reread the prompt, then ask. Do not invent names.
- Prefer small, targeted changes. Keep file paths explicit in updates.

## Pi workflow

- Use Pi's native strengths: context files, skills, prompt templates, sessions/tree/fork/clone, compaction, and extensions. Do not import external orchestration mechanics unless the user explicitly asks to interoperate with them.
- Pi user config is source-controlled in `~/.dotfiles/pi/` and symlinked into `~/.pi/agent/`. When creating or editing Pi tooling, write the canonical file under `~/.dotfiles/pi/` first, then run `~/.dotfiles/rewire-symlinks.sh` if a new symlink target is needed.
- Put new Pi extensions in `~/.dotfiles/pi/extensions/`, prompt templates in `~/.dotfiles/pi/prompts/`, skills in `~/.dotfiles/pi/skills/`, themes in `~/.dotfiles/pi/themes/`, helper executables in `~/.dotfiles/pi/bin/`, and global instructions/settings/keybindings in `~/.dotfiles/pi/{AGENTS.md,settings.json,keybindings.json}`.
- Do not create durable custom Pi tooling directly under `~/.pi/agent/`; that tree is the runtime/symlink target. Exceptions are secrets, auth, sessions, npm/git package caches, and other machine-local state, which must stay out of git.
- Project instructions live in `AGENTS.md` or `CLAUDE.md`; read the relevant one before substantive work, but translate any harness-specific instructions to Pi-native tools.
- Use prompt templates instead of repeating large free-form rituals: `/plan`, `/debug`, `/prod-debug`, `/review`, `/scope`, `/pickup`, `/ship`, `/handoff`, `/resume`.
- Use `read` for file contents, `bash` for search/list/test commands, `edit` for precise changes, and `write` for new files or full rewrites.
- For large files, search first and read with `offset`/`limit`; do not full-read big files just to find one symbol.
- Batch exploration and edits. Avoid repeated one-off reads/greps when a single search or script can answer the question.

## Session start

1. Check for project `AGENTS.md` first, then `CLAUDE.md` only when no Pi/native instructions exist. Follow project rules through Pi-native tools.
2. Check git status and current branch before editing.
3. For new non-trivial work, prefer a feature/fix/refactor branch. Use Pi `/tree`, `/fork`, or `/clone` for alternate approaches instead of starting external workers by habit.
4. If secrets are needed, check `.env.local` then `.env`; never print or hardcode secret values.

## Pi session discipline

- Before risky refactors, uncertain fixes, vendor-debug branches, or competing approaches, create a Pi session branch with `/tree`, `/fork`, or `/clone` rather than starting over in a separate harness.
- Prefer `/compact` when context grows but the active path is still coherent. Prefer `/handoff` when another session/person may pick it up or when tool count is getting high.
- Write handoffs before big transitions: after root cause is found, before shipping, before changing strategy, or around 100 tool calls in one session.
- If three tool calls fail for the same reason, stop and minimize the failure. Do not keep retrying variants blindly.
- Keep final updates self-contained: changed files, focused tests, commands/results, remaining risks.

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

## Tickets and handoffs

- Local ticket briefs live under `$PI_TICKETS_DIR` when set, otherwise `~/.pi/tickets/<project>/`. (`$TICKETS_DIR` is Claude's home, `~/.claude/tickets/<project>/` — do not write Pi briefs there.)
- Linear has no MCP in this harness. Do not look for Linear MCP tools, query Linear GraphQL directly, inspect `$LINEAR_API_KEY`, or manually discover team/label IDs.
- Linear is a write-only sink via `~/.dotfiles/scripts/linear-ticket.py` only. Use named args; the script resolves team, state, assignee, and label names itself.
- Create Linear tickets only from authorized workflows (`/ship` PR reference ticket, bugfinder confirmed bug) with `LINEAR_TICKET_CREATE_OK=1 ~/.dotfiles/scripts/linear-ticket.py create ...`.
- Handoffs should be written to `~/.pi/agent/handoffs/` by default.
- Pi skills are the source of specialized workflows. Load the matching skill before TDD, diagnosis, handoff, production integration debugging, or converting plans to tasks.
