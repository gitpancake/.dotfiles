# Global Instructions

## Verify Before Acting

Before stating ANYTHING re fn signatures, paths, API shapes, event types, env vars, field names, modules, lib methods — **grep/read source first.** Training stale. Code = truth.

Uncertain: 1) grep source 2) re-read brief 3) re-read prompt 4) ask. No guesses, no invented names.

## Tone

Direct, terse, opinionated. Match user energy. No disclaimers/hedging/preamble.

## Subagents & Slash Commands

Self-describe via Agent/skills schemas — don't list. Run `/simplify` at chunk boundaries (orchestrator only). Org preamble: known org codebase → prepend `~/.claude/org/<org>/preamble.md`.

**Lane work → slash command, never manual.** Picking up a ticket/epic, shipping, addressing feedback = always the slash command (`/pickup`, `/epic`, `/scope`, `/ship`, `/address-feedback`). Never hand-roll the equivalent (manual `git worktree add` + branch, raw Agent spawn for the lane). The command owns worktree/branch/lane creation — a manual worktree collides with `wt`'s own and gets the lane killed. If unsure a command covers the task, invoke it and let it decide. (Read-only Explore/research agents are exempt — this is about lane lifecycle, not all agents.)

## Ticket Lifecycle

**Source of truth: `$TICKETS_DIR`. NOT Linear.** Layout: `~/.claude/tickets/<project>/<area>/...` — one centralized home tree, project subfolder = git repo basename. `$TICKETS_DIR` auto-sets via zsh `chpwd` hook when inside a project repo; outside repos / when unset, tools fall back to flat `~/.claude/tickets/`. Status/scope/progress/"what's left" → read local tree (`ls`/`grep`/`Read`). Never read state from Linear — lags + duplicates local. Linear has no MCP here: it's a write-only sink reached by `~/.dotfiles/scripts/linear-ticket.py` (GraphQL + `$LINEAR_API_KEY`) — `/ship` creates the PR's ticket, agents post comments. User says "ticket"/"epic"/"AE-####" → check `$TICKETS_DIR` first, Linear never.

`$TICKETS_DIR` = DB. Contract: its `README.md`. Slug filename; epic = folder w/ `_epic.md`. Brief missing → `/scope` it.

**Slug rule.** No numbers in ticket/epic slugs. Use descriptors, not IDs. `pr3475-split` → `pr-token-pricing-split`. `issue-1284-fix` → `fix-auth-timeout`. Reason: IDs rot (PR# changes pre-merge, issue# meaningless out of tracker), descriptors carry meaning when grepping `tickets/`. Exception: epic-child file ordering prefix (`NN-<child>.md`) — structural, not part of slug.

- **Single**: `/scope` → brief `<area>/<slug>.md`. `wt <slug>` (or `/pickup <slug> <BASE> [ctx]`) → autonomous lane: reads brief, plans slices, uses `grill-with-docs`/`tdd`/`handoff`, commits per layer, `/ship`.
- **Epic**: `/scope` → `<area>/<epic-slug>/_epic.md` + `NN-<child>.md`. `/epic <slug> <BASE> [ctx]` confirms order + spawns `wt --ralph`. Ralph: one story/iteration, fresh context, memory via git + `progress.txt` + `prd.json`. `epic-parse.sh` projects `_epic.md` → `prd.json`. Executes confirmed list, never decomposes.

**Autonomous semantics.** `wt` = fire-and-forget. Stops only on: (1) PR opened + review triggered, (2) blocker (ambiguity not in brief, repeated test fail same cause, missing cred). Slice protocol + parallel gotchas: `~/.dotfiles/CLAUDE.md`.

## Session Start

1. Read project CLAUDE.md. None → scan repo, create.
2. Check OV for context.
3. `git status` + branch. Feature branch for new work.
4. `~/.claude/org/` org folder → apply `context.md`.

## Code Quality

- Guard clauses, early return. Max 2 levels deep.
- One task/fn. Parses+computes+formats → split.
- Specific names: `fetchUserProfile` not `getData`. No `tmp`/`data`/`result`.
- Bools as assertions: `isValid`, `hasChildren`. Ranges: `first`/`last`.
- Complex conditions → named bools.
- `const` default. Declare near first use.
- No code comments. Names + structure carry intent. Exceptions: license headers, tooling pragmas (`eslint-disable`, `ts-expect-error`, `@ts-ignore`), and public-API doc blocks (JSDoc/docstring) where the toolchain consumes them.
- Composition > inheritance. Narrow interfaces.

Detail: OV `resources/agents/code-structure-reference`.

## Cost Discipline

Tool calls re-read full context. Loops compound.

- Batch: one LLM call → plan, script applies. Never same tool 20+ times.
- Opus default. Haiku only bulk mechanical (20+ identical edits).
- >70% context or >50 tool calls → `/handoff` + `/clear`.
- `Read` files >500 lines: use `offset`/`limit`. Never full-read a big file to find one symbol — grep first, then targeted read. Same for log dumps, JSON fixtures, transcripts.

## Turn-Cap Protocol

`turn-cap-warn.sh` hard-halts turn 20. Soft turn 15. `auto-handoff.sh` writes `~/.claude/handoffs/` at 20 (or ctx ≥300k) → `/clear` safe, `/resume` reads back. `clear-handoff.sh` (SessionEnd reason=clear) captures state on any `/clear` ≥5 turns / ≥100k ctx, even below the cap.

- **15 soft**: wrap in-flight. No new scope.
- **20 HARD HALT** by cwd:
  - Normal: tell user `/clear`. No tools.
  - `wt` lane (`<repo>/.claude/worktrees/`): one `git add -A && git commit` max, stop. User runs `/resume` in fresh lane.
  - Ralph lane (lane + `scripts/ralph/`): end iteration silently. `ralph.sh` spawns next w/ fresh ctx.
- **Past 20**: directive re-fires every prompt; `handoff-gate.sh` blocks tools until a handoff doc exists. Cost = quadratic. No push-through.

`/handoff` skill = richer; auto doc = safety net.

## Briefs & PRDs

Re-read every lane resume / loop iteration — compounds. Brief = context + acceptance criteria. `## Local notes` = decisions, not narration. Ralph stories sized to one context window.

## Git Workflow

- Branches: `feature/`, `fix/`, `refactor/`. Never `user/`. Main deployable.
- Auto-commit per chunk. Separate: schema, backend, frontend.
- Never push unless asked. PR title <70 chars. Squash merge.
- Worktree default for non-trivial. Cleanup only on confirmed merge.
- **Open PR via `/ship`, never raw `gh pr create`.** `/ship` §2.5 creates the PR's Linear team-reference ticket (composed from real commits+diff) via `scripts/linear-ticket.py create`. Hand-rolling the PR skips the ticket and the team loses the reference.

## Secrets / Env

Need API key, token, or env var → check `.env.local` (project root) first, then `.env`. Don't ask the user for a value that's already there. Never hardcode secrets, never echo a full key to output/logs/commits — reference by name (`$OPENAI_API_KEY`), mask when shown. Missing from both → ask.

## Project CLAUDE.md

After each chunk: update project `CLAUDE.md` (conventions, decisions, gotchas). Update `README.md` if user-facing behavior changes. ≤150 lines. Cut anything derivable from code.

## OpenViking

Vector-indexed MCP: cross-project knowledge, external API docs, research.

**Not for**: project context (CLAUDE.md), work summaries (git), user prefs (auto-memory).

**MANDATORY**: Before `WebFetch`/`WebSearch`/`context7` for API docs → `find`/`search` OV first. Not found → fetch + `add_resource`.

`mcp__openviking__ls` at `resources/` to discover. List before assuming paths.

Namespaces: `resources/agents/`, `resources/<project>/`, `resources/<api-name>/`.
