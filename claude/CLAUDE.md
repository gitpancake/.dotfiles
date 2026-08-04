# Global Instructions

## Verify Before Acting

Before stating ANYTHING re fn signatures, paths, API shapes, event types, env vars, field names, modules, lib methods — **grep/read source first.** Training stale. Code = truth.

Uncertain: 1) grep source 2) re-read brief 3) re-read prompt 4) ask. No guesses, no invented names.

## Tone

Direct, terse, opinionated. Match user energy. No disclaimers/hedging/preamble.

**Compressed replies (caveman), always on.** Drop articles/filler/pleasantries. Fragments OK. Abbreviate (DB/auth/config/fn/impl), arrows for causality (X → Y), one word when one word enough. Technical terms exact; errors quoted exact; code blocks unchanged. Write NORMAL prose for: code/commits/PR bodies/tickets, security warnings, irreversible-action confirmations, multi-step sequences where fragment order risks misread. "stop caveman" / "normal mode" → revert.

## Subagents & Slash Commands

Self-describe via Agent/skills schemas — don't list. Org preamble: known org codebase → prepend `~/.claude/org/<org>/preamble.md`.

**Lane work → slash command, never manual.** Picking up a ticket/epic, shipping, addressing feedback = always the slash command (`/pickup`, `/epic`, `/scope`, `/ship`, `/address-feedback`). Never hand-roll the equivalent (manual `git worktree add` + branch, raw Agent spawn for the lane). The command owns worktree/branch/lane creation — a manual worktree collides with `wt`'s own and gets the lane killed. If unsure a command covers the task, invoke it and let it decide. (Exempt: read-only Explore/research agents, and `/resume` — which continues existing work in-session and never spawns. This rule is about *starting* lane work.)

## Ticket Lifecycle

**Source of truth: Linear.** Read AND write via the **`linear` skill** (arbitrary GraphQL via `~/.dotfiles/scripts/linear-gql.py`); `~/.dotfiles/scripts/linear-ticket.py` stays the fast path for `create`/`comment`/`state`. Local ticket tree RETIRED 2026-08-04 — `$TICKETS_DIR` survives only as a lane materialization cache (below), never a source of truth; no MCP either (skill covers everything). Status/scope/progress/"what's left" → query Linear. User says "ticket"/"epic"/"AOA-###"/"ENGH-###" → look it up in Linear.

**Shapes & template.** Single ticket = Linear **issue**; the description IS the brief and follows the house template (`docs/engineering-linear-template.md` in cartage-agent): **Requirement** (user-facing outcome, 2-3 sentences) → **Context** (why) → **Acceptance Criteria** (checkboxes, each a testable yes/no — never "works correctly") → **Limitations** (out of scope, each WITH its why — kills scope creep + relitigating) → **Proof** (defined BEFORE work starts: Manual Tests as concrete steps/evidence, Automated Tests to be added; ticket missing Proof → ask "what will you show to prove this works?") → **Signatures** (@product approves AC/Limitations/Proof, @owner confirms manual tests local+prod, @eng final; real names when known). Engineered `/scope` briefs add Surface area + Reversibility. Epic = Linear **project**: same template at project level (Requirement / Context / AC / Limitations / Size & Order), children = issues carrying per-story detail, **blocking relations mirror the dependency DAG**, fib estimates summing to the stated time budget. Exemplar: off-git `c9bdadb3cdfc` (ENGH-335..343). **Prose style: Write Simply** (paulgraham.com/simply.html) — short sentences, plain words, decode internal shorthand in place ("a tombstone revision, so history survives"), keep exact technical names (paths, workflows, flags) verbatim. Linear content is self-contained: NO local paths (`~/.claude/...`), no references to local ticket files.

**Linear teams.** Engineering epics/stories → **ENGH** (`Engineering`). Agent-created work → **AOA** (`AO - Agents`): `/ship`'s PR ticket, `bugfinder`'s bugs, everything Chuck/Kelly write (`LINEAR_TEAM_KEY=AOA`). Human ops work → **AO** (`Autonomy Operations`), the `linear-ticket.py --team` default. **`AE`/`Autonomy Eng` is RETIRED** — creating there fails `Entity is retired: team`, and listing teams still shows it, so only a create attempt reveals this. Old `AE-####` ids stay valid and are reconciled in place; never re-create them on AOA. A create that fails → report and continue unprefixed, never substitute a team on your own.

**Lane bridge.** `wt` reads a brief file on disk. `~/.dotfiles/scripts/linear-brief.sh <ID>` materializes a Linear issue's description into `$TICKETS_DIR` (frontmatter `linear: <ID>`) so `wt`/`/pickup` can resolve + spawn. The file is a **disposable cache**: scope edits go to Linear (`/rescope`), then delete + re-materialize. `## Local notes` appended by lanes = lane scratch, never scope. Ticket has no brief in Linear → `/scope` it.

**Slug rule.** Applies to branch names + materialized brief filenames: no numbers, descriptors not IDs. `pr3475-split` → `pr-token-pricing-split`. `issue-1284-fix` → `fix-auth-timeout`. Reason: IDs rot (PR# changes pre-merge, issue# meaningless out of tracker). Everywhere else the Linear id (`ENGH-###`) is the canonical handle.

- **Single**: `/scope` → Linear issue (grill-with-docs runs inside /scope, lanes do not re-grill). `/pickup <ID> <BASE> [ctx]` (or `wt <ID>` after materializing) → autonomous lane: reads brief, plans slices, opens `/tdd` for behavior-changing slices, commits per layer, `/handoff` at ~240K ctx, `/ship`.
- **Epic**: `/scope` → Linear project + child issues + blocking DAG. `/epic <project> <BASE>` reads child states from Linear, confirms order, spawns the next unblocked child as a single lane.

**Autonomous semantics.** `wt` = fire-and-forget; the lane OWNS its review loop end-to-end (reviews fire automatically on PR push — Arbiter/Devin/Codex; Chuck retired). **In a lane, or spawning one: READ `~/.claude/docs/lane-protocol.md` first** — it owns the review loop, stop conditions, and the handoff contract (`lane-done.sh` / `lane-handoff.sh` as final tool call).

## Tool Routing: Skills First, MCP Fallback

Domain covered by a local skill or script → use it FIRST; MCP is the fallback, never the first reach. Mapping: Axiom → `axiom-api` skill, LangSmith → `langsmith-api` / `/langsmith`, Linear → `linear` skill / `linear-ticket.py`, Slack reads/cleanup → `cartage-bots`, Wilson store → `wilson-memories`, meetings → `granola`/`pocket`, paging → `rootly`. Skills carry the auth quirks, response-shape handling, and cost discipline the raw MCP tools lack; MCP schemas also bloat context via ToolSearch. Only fall back to `mcp__*` when the skill path genuinely fails (missing capability, hard auth error) — and say so when you do. No skill covers the domain (Sentry, Notion, PostHog, Playwright, Trigger, gcloud) → MCP fine directly.

## Shell Gotchas (zsh)

No `timeout`/`gtimeout` on this Mac (BSD userland, coreutils not installed) — `timeout N cmd` fails exit 127. Bound long commands with a `for`/`until` loop + `sleep`, the Bash tool's `timeout` param, or `run_in_background`.

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
- `Read` files >500 lines: use `offset`/`limit`. Never full-read a big file to find one symbol — grep first, then targeted read. Same for log dumps, JSON fixtures, transcripts.
- After an `Edit`, never full-re-read the file — the edit result is already in context. Verify via the edited range only (`offset`/`limit`). Applies hardest to TDD loops: test file does NOT need a fresh Read per red-green cycle.
- Subagent dispatch: compute shared setup once (tokens, env, IDs) and inline the *values* into the prompt — sibling agents must never re-derive. Anything poll-shaped = ONE bounded `until`/`for`+`sleep` Bash loop (or Monitor), never N repeated calls.

## Context Cap

Cost driver = context size × agentic-loop length, NOT user turns (turn cap retired 2026-06-09 — fired once in 14d while lanes ran 300+ assistant msgs per turn, invisible to it).

- **Cockpit**: watch the statusline ctx bar. >70% ctx or >50 tool calls → `/handoff` + `/clear` at the next task boundary. `clear-handoff.sh` (SessionEnd reason=clear) captures state on any `/clear` ≥5 turns / ≥100k ctx — mechanical net; a deliberate `/handoff` beats it.
- **Lane**: ctx nudges at 260K/320K/380K; on-nudge rules (finish-vs-handoff, `lane-handoff.sh` contract) live in `~/.claude/docs/lane-protocol.md`. Never compact in a lane.

## Briefs & PRDs

Brief = Linear issue description: context + acceptance criteria. Re-read every lane resume / loop iteration — compounds. Epic child stories sized to one context window. `## Local notes` in the materialized cache file = lane decisions, not narration — never treat as scope.

## Git Workflow

- Branches: `feature/`, `fix/`, `refactor/`. Never `user/`. Main deployable.
- Auto-commit per chunk. Separate: schema, backend, frontend.
- Never push unless asked. PR title <70 chars. Squash merge.
- Worktree default for non-trivial. Cleanup only on confirmed merge.
- **Open PR via `/ship`, never raw `gh pr create`.** `/ship` §2.5 creates the PR's Linear team-reference ticket (composed from real commits+diff) via `scripts/linear-ticket.py create`. Hand-rolling the PR skips the ticket and the team loses the reference.

## Secrets / Env

Need API key, token, or env var (for a tool call or otherwise) → check `.env.local` (project root) first, then `.env`, then the cross-project shared stores `~/.claude/.env` and `~/.pi/.env` (LangSmith, Axiom, etc; source with `set -a; . ~/.claude/.env; . ~/.pi/.env 2>/dev/null; set +a`). Don't ask the user for a value that's already there. Never hardcode secrets, never echo a full key to output/logs/commits — reference by name (`$OPENAI_API_KEY`), mask when shown. Missing from all → ask. (Per-API auth quirks live in the matching skill — e.g. `langsmith-api` for the dual-header requirement.)

## Project CLAUDE.md

After each chunk: update project `CLAUDE.md` (conventions, decisions, gotchas). Update `README.md` if user-facing behavior changes. ≤150 lines. Cut anything derivable from code.

