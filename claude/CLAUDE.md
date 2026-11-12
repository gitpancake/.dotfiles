# Global Instructions

## Verify Before Acting

Before stating ANYTHING re fn signatures, paths, API shapes, event types, env vars, field names, modules, lib methods — **grep/read source first.** Training stale. Code = truth.

Uncertain about a fact: grep source → re-read brief → re-read prompt. Ask only when the code can't answer. No guesses, no invented names.

## Act, Don't Offer

Reversible or read-only next step → do it, then report. That covers: Linear description/comment edits, prod and log reads, status re-checks, running the script just discussed, fixing the thing just diagnosed. Never close on "Want me to…?", "Say the word", "Affirm or override", "Which one?" for those — the answer is always yes and the round trip is the cost. Confirm first only for irreversible or outward actions: prod writes, force-push, deletes, messages to customers/Slack, paid review rounds.

## Tone

Direct, terse, opinionated. Match user energy. No disclaimers/hedging/preamble.

**Closers carry no advisory trailers.** No "Worth…", "One caveat…", "Heads-up…", "Separately…". If it changes the user's next action it goes in the body; otherwise cut. Stop when the content stops.

**Compressed replies (caveman), always on.** Drop articles/filler/pleasantries. Fragments OK. Abbreviate (DB/auth/config/fn/impl), arrows for causality (X → Y), one word when one word enough. Technical terms exact; errors quoted exact; code blocks unchanged. Write NORMAL prose for: code/commits/PR bodies/tickets, security warnings, irreversible-action confirmations, multi-step sequences where fragment order risks misread. "stop caveman" / "normal mode" → revert.

**Explanations, and anything I will paste, are written simply.** When I ask why or how, or say I am confused — and for any Slack post, update, summary, or doc I will hand to someone — write short full sentences in plain words (paulgraham.com/simply.html). Answer first. A yes/no question gets yes or no as its first word. Twelve lines at most unless I ask for more. No headers or tables in an answer to one question. Caveman stays for status and ops chatter.

## Diagnosis

A root cause is a claim about what the failing thing is doing right now. Earn it by reading that thing.

- **Read the failing thing first.** The live row, the run, the deployed commit, the vendor's response, the failed step's own error. Code that should produce the behaviour is not the behaviour.
- **Check you are looking at now.** `git fetch origin && git status -sb` before quoting a file as current behaviour; a checkout behind `origin/main` is history. Then search merged PRs from the last 48 hours, Linear, and memory for the symptom. The fix is often already shipped.
- **Mark every causal sentence Observed or Inferred.** Observed: I ran this, and here are the 3–10 lines of output that show it. Inferred: it follows from X, and Y is the check that would confirm it.
- **Only an Observed cause gets the `Root cause: <layer>` line** (`prompt:<skill|memory|global rule>` or `code:<path>`), placed before any fix list. Otherwise close with `Leading hypothesis:` and the one check that splits it from the runner-up. If that check is read-only, run it before replying.
- **A subagent's or a lane's finding is Inferred** until you have read its evidence yourself.
- **Nothing is built on an Inferred cause.** No ticket, lane, fix, config change, or message to a person.
- **Pushback means go and read.** "Are you sure?" is not a request for a second theory. A new story with no new evidence is the same mistake twice.

## Pace

The bar is a lower defect rate, not more PRs.

- **Three lanes at once.** `WT_MAX_LANES=3`. A fourth waits.
- **I write the Requirement and the Limitations.** `/scope` grills them and fills in the rest. It never drafts those two.
- **Reader's brief before "merge".** Six lines I could say out loud: what behaviour changes, what was deleted, who owned it, what breaks if this is wrong, how it was proven, what was not tested. Print it when I say "merge". No brief, no merge.
- **Rip-out check.** Before deleting something another person built: name the owners (`git log --format=%an -- <paths> | sort | uniq -c`), show that live usage is zero or list who still uses it, and draft the heads-up to the owner. The message goes out before the PR does.
- **One hat per PR.** A behaviour change and a cleanup (comment strip, rename, move) ship separately, cleanup first.

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

**Review-gate polling is ONE tool call, through Monitor:** `git push && ~/.claude/scripts/devin-review.sh gate <PR-url>; echo GATE_EXIT=$?` run with the Monitor tool (`timeout_ms: 900000`). The script sleeps internally; under Monitor the lane stays reachable for follow-ups and the last line carries the exit code. A lane's Bash tool has no `run_in_background` (`claude-lane` disables background tasks), and the guard hook denies a foreground Bash gate. Never `sleep 90 && …status`, never `for i in $(seq …); do gh pr checks …`, never `devin-review.sh status` in a loop — each is a full-context turn spent reading "pending", and it's where lanes get killed from the cockpit. Timed out (exit 4) → call `gate` once more, then `lane-pause.sh review`.

## Tool Routing: Skills First, MCP Fallback

Domain covered by a local skill or script → use it FIRST; MCP is the fallback, never the first reach. Mapping: Axiom → `axiom-api` skill, LangSmith → `langsmith-api` / `/langsmith`, Linear → `linear` skill / `linear-ticket.py`, Slack reads/cleanup → `cartage-bots`, Wilson store → `wilson-memories`, meetings → `granola`/`pocket`, paging → `rootly`, Sentry → `sentry-api`, PostHog → `posthog-api`, Trigger.dev → `trigger-api`, Attio → `attio-api`, Firestore dev/prod → `prod-firestore`, prod app Postgres → `prod-postgres` (read-only role, no write URL on this machine), gcloud → CLI direct via Bash (no MCP). Skills carry the auth quirks, response-shape handling, and cost discipline the raw MCP tools lack; MCP schemas also bloat context via ToolSearch. Only fall back to `mcp__*` when the skill path genuinely fails (missing capability, hard auth error) — and say so when you do. No skill covers the domain (Notion, Playwright) → MCP fine directly.

## Shell Gotchas (zsh)

**App processes run bare, foreground.** Anything that boots the app or a script — `bun type-check`, `bun test`, `bun run script`, `bunx`, `node` — never `| tail`, never `| head`, never `run_in_background`. Output too big → `cmd > out.log 2>&1`, then grep/tail the *file* in a separate call. **Never `tail -f`** — it never exits, the Bash tool can only time out on it; poll with `tail -n 40 file` in a bounded `for`+`sleep` loop. The `tail-pipe-guard` hook denies all of these — a denial means fix the shape, not retry it. (Why: on this Mac a backgrounded pipe's write end stays open after the command exits, so `tail` blocks forever at zero output; `ps` shows only `tail` alive. That's the pipe, not a hung DB/network call.)

**zsh reserves `status` (read-only).** Never name a variable `status` — `(eval): read-only variable: status`. Use `state`, `verdict`, `checkStatus`.

No `timeout`/`gtimeout` on this Mac (BSD userland, coreutils not installed) — `timeout N cmd` fails exit 127. Bound long commands with a `for`/`until` loop + `sleep`, the Bash tool's `timeout` param, or `run_in_background`.

The Bash tool runs zsh. zsh `echo` expands backslash escapes — `echo "$json" | jq` corrupts any JSON whose strings contain `\n`/`\t`/`\uXXXX` (PR comment bodies always do) → `jq: parse error: control characters from U+0000 through U+001F must be escaped`. Never round-trip JSON through `echo`. Use `gh ... --jq '...'` directly, pipe without a variable (`gh ... | jq`), or `printf '%s' "$json" | jq`.

**Never invoke a CLI that may prompt interactively (inquirer, npm init, `bun run script` with an unfilled `confirm`/`input` param, etc.) without passing every required value via flag.** There is no real TTY in this environment — a missing flag that triggers a prompt hangs the process forever reading from `/dev/null` (or from a piped `printf`, which most prompt libraries also can't read as keystrokes). It looks identical to a slow command: `run_in_background` reports it as still running, and it never produces the tool's actual output. Tell: the tool's setup/boot log printed fine, then stopped mid-render on a prompt line, and no completion message ever follows. Fix: pass every param the CLI could ask for, even boolean ones — for a Commander `Option` defined as a bare flag (no `<value>`) there is usually no `--no-x` negation unless the tool explicitly registered one, so a flag that must be `false` may be impossible to set via CLI at all; in that case skip the CLI layer entirely and call the underlying function directly in a small one-off script (reproduce whatever env/secrets bootstrap the CLI normally does first).

## Session Start

1. Read project CLAUDE.md. None → scan repo, create.
2. `git status` + branch. Feature branch for new work.
3. `~/.claude/org/` org folder → apply `context.md`.

## Code Quality

- **NO comments — code explains itself.** Never introduce a comment; never keep one you can delete. Tempted to comment → rename/extract until the code says it (per Bob Martin, Clean Code ch.4: every comment is a failure to express intent in code). Only exceptions: license headers, tooling pragmas (`eslint-disable`, `ts-expect-error`, `@ts-ignore`), public-API doc blocks (JSDoc/docstring) the toolchain consumes, and warning-of-consequences a name can't carry (irreversible op, ordering constraint). Any surviving comment explains why, never what. Touching a file → delete comments that restate readable code.
- Guard clauses, early return. Max 2 levels deep.
- One task/fn. Parses+computes+formats → split.
- Specific names: `fetchUserProfile` not `getData`. No `tmp`/`data`/`result`.
- Bools as assertions: `isValid`, `hasChildren`. Ranges: `first`/`last`.
- Complex conditions → named bools.
- `const` default. Declare near first use.
- Composition > inheritance. Narrow interfaces.

## Design Principles

Reference: `~/.claude/docs/design-principles.md`. Cite by tag (`POSD §X` / `PP §Y`) when justifying a change. Pull the doc when arguing scope, code-review pushback, or structural choices. Reducing complexity beats any single rule.

## Cost Discipline

Tool calls re-read full context. Loops compound.

- Batch: one LLM call → plan, script applies. Never same tool 20+ times.
- Opus cockpit default. Lanes run Sonnet (`WT_MODEL=claude-sonnet-5-5` from `.zshenv`; `WT_MODEL=opus wt …` per lane when reasoning-heavy — wt puts it on the agent command, so verify with the session jsonl's `"model"`, not `ps`). Haiku only bulk mechanical (20+ identical edits).
- `Read` files >500 lines: use `offset`/`limit`. Never full-read a big file to find one symbol — grep first, then targeted read. Same for log dumps, JSON fixtures, transcripts.
- After an `Edit`, never full-re-read the file — the edit result is already in context. Verify via the edited range only (`offset`/`limit`). Applies hardest to TDD loops: test file does NOT need a fresh Read per red-green cycle.
- Subagent dispatch: compute shared setup once (tokens, env, IDs) and inline the *values* into the prompt — sibling agents must never re-derive. Anything poll-shaped = ONE bounded `until`/`for`+`sleep` Bash loop (or Monitor), never N repeated calls.

## Context Cap

Cost driver = context size × agentic-loop length, NOT user turns (turn cap retired 2026-06-09 — fired once in 14d while lanes ran 300+ assistant msgs per turn, invisible to it).

- **Cockpit**: watch the statusline ctx bar. >70% ctx or >50 tool calls → `/handoff` + `/clear` at the next task boundary. `clear-handoff.sh` (SessionEnd reason=clear) captures state on any `/clear` ≥5 turns / ≥100k ctx — mechanical net; a deliberate `/handoff` beats it.
- **Lane**: ctx nudges at the tiers in `~/.claude/lane.config` (higher once a PR is open); on-nudge rules (finish-vs-handoff, `lane-handoff.sh` contract) live in `~/.claude/docs/lane-protocol.md`. Never compact in a lane.

## Briefs & PRDs

Brief = Linear issue description: context + acceptance criteria. Re-read every lane resume / loop iteration — compounds. Epic child stories sized to one context window. `## Local notes` in the materialized cache file = lane decisions, not narration — never treat as scope.

## Git Workflow

- **Local `main` is read-only — never commit to it, in any cartage repo.** Both ai-employees and cartage-agent gate `main` behind required status checks (verified 2026-09-01), so a direct push is always rejected: a local-main commit strands as unpushable noise lanes never see (they branch off `origin/main`) and wedges `wt` fast-forwards. Everything lands branch → PR — docs included (`CONTEXT.md` pins ride `/scope` §7's throwaway-worktree docs-PR, exempt from `/ship`'s ticket). Local main found ahead of origin → lift the commits onto a branch, PR + merge, then `git reset --hard origin/main`.
- Branches: `feature/`, `fix/`, `refactor/`. Never `user/`. Main deployable.
- Auto-commit per chunk. Separate: schema, backend, frontend.
- Never push unless asked. PR title <70 chars. Squash merge.
- Worktree default for non-trivial. Cleanup only on confirmed merge.
- **Sibling lanes + main moves → `/rebase-all` from the cockpit.** Never relay "main moved to <sha>" into lane panes by hand, never have each lane poll main and rebase itself; one cockpit pass fans the rebases and force-pushes clean replays.
- **Open PR via `/ship`, never raw `gh pr create`.** `/ship` §2.5 creates the PR's Linear team-reference ticket (composed from real commits+diff) via `scripts/linear-ticket.py create`. Hand-rolling the PR skips the ticket and the team loses the reference.

## Secrets / Env

Need API key, token, or env var (for a tool call or otherwise) → check `.env.local` (project root) first, then `.env`, then the cross-project shared stores `~/.claude/.env` and `~/.pi/.env` (LangSmith, Axiom, etc; source with `set -a; . ~/.claude/.env; . ~/.pi/.env 2>/dev/null; set +a`). Don't ask the user for a value that's already there. Never hardcode secrets, never echo a full key to output/logs/commits — reference by name (`$OPENAI_API_KEY`), mask when shown. Missing from all → ask. (Per-API auth quirks live in the matching skill — e.g. `langsmith-api` for the dual-header requirement.)

## Project CLAUDE.md

After each chunk: update project `CLAUDE.md` (conventions, decisions, gotchas). Update `README.md` if user-facing behavior changes. ≤150 lines. Cut anything derivable from code.

**Clean instructions** (Clean Code transposed — applies to any CLAUDE.md, prompt, or agent brief you write):

- Don't hedge a vague rule — rewrite it. Three caveats = the rule isn't clear.
- State intent + constraints, never implementation steps. The worker can read the code.
- A footnote/exception is a failure of the main instruction — fold it in.
- Every line must change what gets produced. Cut what the model already knows.
- One rule per bullet, one concern per section.

