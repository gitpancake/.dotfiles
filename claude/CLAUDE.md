# Global Instructions

## Verify Before Acting

Before stating ANYTHING re fn signatures, paths, API shapes, event types, env vars, field names, modules, lib methods — **grep/read source first.** Training stale. Code = truth.

Uncertain: 1) grep source 2) re-read brief 3) re-read prompt 4) ask. No guesses, no invented names.

## Tone

Direct, terse, opinionated. Match user energy. No disclaimers/hedging/preamble.

**Compressed replies (caveman), always on.** Drop articles/filler/pleasantries. Fragments OK. Abbreviate (DB/auth/config/fn/impl), arrows for causality (X → Y), one word when one word enough. Technical terms exact; errors quoted exact; code blocks unchanged. Write NORMAL prose for: code/commits/PR bodies/tickets, security warnings, irreversible-action confirmations, multi-step sequences where fragment order risks misread. "stop caveman" / "normal mode" → revert.

## Subagents & Slash Commands

Self-describe via Agent/skills schemas — don't list. Org preamble: known org codebase → prepend `~/.claude/org/<org>/preamble.md`.

**Lane work → slash command, never manual.** Picking up a ticket/epic, shipping, addressing feedback = always the slash command (`/pickup`, `/epic`, `/scope`, `/ship`, `/address-feedback`). Never hand-roll the equivalent (manual `git worktree add` + branch, raw Agent spawn for the lane). The command owns worktree/branch/lane creation — a manual worktree collides with `wt`'s own and gets the lane killed. If unsure a command covers the task, invoke it and let it decide. (Read-only Explore/research agents are exempt — this is about lane lifecycle, not all agents.)

## Ticket Lifecycle

**Source of truth: `$TICKETS_DIR`. NOT Linear.** Layout: `~/.claude/tickets/<project>/<area>/...` — one centralized home tree, project subfolder = git repo basename. `$TICKETS_DIR` auto-sets via zsh `chpwd` hook when inside a project repo; outside repos / when unset, tools fall back to flat `~/.claude/tickets/`. Status/scope/progress/"what's left" → read local tree (`ls`/`grep`/`Read`). Never read state from Linear — lags + duplicates local. Linear has no MCP here: it's a write-only sink reached by `~/.dotfiles/scripts/linear-ticket.py` (GraphQL + `$LINEAR_API_KEY`) — `/ship` creates the PR's ticket, agents post comments. User says "ticket"/"epic"/"AE-####" → check `$TICKETS_DIR` first, Linear never.

`$TICKETS_DIR` = DB. Contract: its `README.md`. Slug filename; epic = folder w/ `_epic.md`. Brief missing → `/scope` it.

**Slug rule.** No numbers in ticket/epic slugs. Use descriptors, not IDs. `pr3475-split` → `pr-token-pricing-split`. `issue-1284-fix` → `fix-auth-timeout`. Reason: IDs rot (PR# changes pre-merge, issue# meaningless out of tracker), descriptors carry meaning when grepping `tickets/`. Exception: epic-child file ordering prefix (`NN-<child>.md`) — structural, not part of slug.

- **Single**: `/scope` → brief `<area>/<slug>.md` (grill-with-docs runs inside /scope, lanes do not re-grill). `wt <slug>` (or `/pickup <slug> <BASE> [ctx]`) → autonomous lane: reads brief, plans slices, opens `/tdd` for behavior-changing slices, commits per layer, `/handoff` at ~120K ctx, `/ship`.
- **Epic**: `/scope` → `<area>/<epic-slug>/_epic.md` + `NN-<child>.md`. Ralph loop retired 2026-06-09 (`wt --ralph` + `epic-parse` removed from wt-lanes) — pick up children as single lanes in `NN` order via `/pickup <child-slug>`.

**Autonomous semantics.** `wt` = fire-and-forget, and the lane OWNS its review loop end-to-end: `/ship` → trigger review → poll for the bot's comment → address ALL findings (blockers → nits) on the PR branch, commit + push → `~/.claude/scripts/lane-done.sh` as the final tool call (writes `DONE`, flashes the lane's tmux window green). Stops only on: (1) feedback fully addressed + pushed (or review skipped per repo policy) + `lane-done.sh` run, (2) blocker (ambiguity not in brief, repeated test fail same cause, missing cred), (3) review never lands within ~15 min of polling → `lane-pause.sh review 'PR #<N> review pending'`, stop without claiming done, (4) ctx nudge fired with a full slice still remaining → `/handoff` + `~/.claude/scripts/lane-handoff.sh <doc>` as the final tool call — lane-run.sh respawns a fresh session that `/resume`s the doc; a review-only remainder NEVER justifies a handoff (it's one poll loop + one feedback pass — finish it). A `/handoff` without the `lane-handoff.sh` state write strands the lane: nothing respawns. Feedback is NEVER deferred to a separate lane. Tix repo review policy: Chuck reviews `cartage-agent` + `ai-employees` (tag `@chuck-noland-cartage review` on the PR); other repos skip review + loop. **Chuck's review = single issue comment from `chuck-noland[bot]` (body starts `**Chuck finished`; section header varies — `### Review — <title>` / `### Chuck review` — so match author + opener, never the header; 🔴 = blocker, "Advisory" = nits), NOT a GitHub Review object** — to find it, read `gh api repos/{owner}/{repo}/issues/<PR>/comments`; `reviews`, `reviewDecision`, and `pulls/<PR>/comments` stay empty forever, so never poll those for Chuck. Slice protocol + parallel gotchas: `~/.dotfiles/CLAUDE.md`.

## Shell Gotchas (zsh)

The Bash tool runs zsh. zsh `echo` expands backslash escapes — `echo "$json" | jq` corrupts any JSON whose strings contain `\n`/`\t`/`\uXXXX` (PR comment bodies always do) → `jq: parse error: control characters from U+0000 through U+001F must be escaped`. Never round-trip JSON through `echo`. Use `gh ... --jq '...'` directly, pipe without a variable (`gh ... | jq`), or `printf '%s' "$json" | jq`.

## Session Start

1. Read project CLAUDE.md. None → scan repo, create.
2. `git status` + branch. Feature branch for new work.
3. `~/.claude/org/` org folder → apply `context.md`.

## Code Quality

- Guard clauses, early return. Max 2 levels deep.
- One task/fn. Parses+computes+formats → split.
- Specific names: `fetchUserProfile` not `getData`. No `tmp`/`data`/`result`.
- Bools as assertions: `isValid`, `hasChildren`. Ranges: `first`/`last`.
- Complex conditions → named bools.
- `const` default. Declare near first use.
- No code comments. Names + structure carry intent. Exceptions: license headers, tooling pragmas (`eslint-disable`, `ts-expect-error`, `@ts-ignore`), and public-API doc blocks (JSDoc/docstring) where the toolchain consumes them.
- Composition > inheritance. Narrow interfaces.

## Design Principles

Reference: `~/.claude/docs/design-principles.md`. Cite by tag (`POSD §X` / `PP §Y`) when justifying a change. Pull the doc when arguing scope, code-review pushback, or structural choices. Reducing complexity beats any single rule.

## Cost Discipline

Tool calls re-read full context. Loops compound.

- Batch: one LLM call → plan, script applies. Never same tool 20+ times.
- Opus cockpit default. Lanes run Sonnet (`WT_MODEL=sonnet`, set by wt-lanes; `WT_MODEL=opus wt …` per lane when reasoning-heavy). Haiku only bulk mechanical (20+ identical edits).
- >70% context or >50 tool calls → `/handoff` + `/clear`.
- `Read` files >500 lines: use `offset`/`limit`. Never full-read a big file to find one symbol — grep first, then targeted read. Same for log dumps, JSON fixtures, transcripts.
- After an `Edit`, never full-re-read the file — the edit result is already in context. Verify via the edited range only (`offset`/`limit`). Applies hardest to TDD loops: test file does NOT need a fresh Read per red-green cycle.
- Subagent dispatch: compute shared setup once (tokens, env, IDs) and inline the *values* into the prompt — sibling agents must never re-derive. Anything poll-shaped = ONE `until`/`timeout` Bash loop (or Monitor), never N repeated calls.

## Context Cap

Cost driver = context size × agentic-loop length, NOT user turns (turn cap retired 2026-06-09 — fired once in 14d while lanes ran 300+ assistant msgs per turn, invisible to it).

- **Cockpit**: watch the statusline ctx bar. >70% → `/handoff` + `/clear` at the next task boundary. `clear-handoff.sh` (SessionEnd reason=clear) captures state on any `/clear` ≥5 turns / ≥100k ctx — mechanical net; a deliberate `/handoff` beats it.
- **Lane** (`<repo>/.claude/worktrees/`): `lane-ctx-nudge.sh` (PostToolUse, non-blocking) injects a reminder at 130K/160K/190K ctx. On nudge: review-only remainder → finish it (one poll + one feedback pass) + `lane-done.sh`, never hand off. Full slice remaining → wrap + commit, `/handoff`, then `~/.claude/scripts/lane-handoff.sh <doc>` as the FINAL tool call — wt-lanes' lane-run.sh respawns a fresh session that `/resume`s the doc and continues the brief, incl. any pending review loop. Skipping `lane-handoff.sh` strands the lane. Never compact in a lane.

## Briefs & PRDs

Re-read every lane resume / loop iteration — compounds. Brief = context + acceptance criteria. `## Local notes` = decisions, not narration. Epic child stories sized to one context window.

## Git Workflow

- Branches: `feature/`, `fix/`, `refactor/`. Never `user/`. Main deployable.
- Auto-commit per chunk. Separate: schema, backend, frontend.
- Never push unless asked. PR title <70 chars. Squash merge.
- Worktree default for non-trivial. Cleanup only on confirmed merge.
- **Open PR via `/ship`, never raw `gh pr create`.** `/ship` §2.5 creates the PR's Linear team-reference ticket (composed from real commits+diff) via `scripts/linear-ticket.py create`. Hand-rolling the PR skips the ticket and the team loses the reference.

## Secrets / Env

Need API key, token, or env var (for a tool call or otherwise) → check `.env.local` (project root) first, then `.env`, then the cross-project shared stores `~/.claude/.env` and `~/.pi/.env` (LangSmith, Axiom, etc; source with `set -a; . ~/.claude/.env; . ~/.pi/.env 2>/dev/null; set +a`). Don't ask the user for a value that's already there. Never hardcode secrets, never echo a full key to output/logs/commits — reference by name (`$OPENAI_API_KEY`), mask when shown. Missing from all → ask.

LangSmith REST: key is workspace-scoped — every request needs BOTH `-H "x-api-key: $LANGSMITH_API_KEY"` AND `-H "X-Tenant-Id: $LANGSMITH_WORKSPACE_ID"`, else `{"detail":"Forbidden"}`.

## Project CLAUDE.md

After each chunk: update project `CLAUDE.md` (conventions, decisions, gotchas). Update `README.md` if user-facing behavior changes. ≤150 lines. Cut anything derivable from code.

