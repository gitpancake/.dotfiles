# Lane Protocol — autonomous `wt` lanes

Single source of truth for the lane lifecycle: spawn → slices → pre-ship self-review →
`/ship` → review loop → done/handoff. Referenced by global CLAUDE.md and `/ship`, `/address-feedback`,
`/why-failing`, `/resume`. Read this when working in a lane (cwd under
`<repo>/.claude/worktrees/`) or spawning one.

## Semantics

`wt` = fire-and-forget. The lane owns its work end-to-end: read the brief, plan slices,
`/tdd` for behavior-changing slices, commit per layer, `/ship`, then the review loop below.
Feedback is NEVER deferred to a separate lane.

## Testing discipline

Test runs are SCOPED to the files your slice touches — never repo-wide. Never run a full
suite or suite-level script: `bun run test:wilson`, bare `bun test` with no path,
`test:all`, or equivalents. In cartage-agent the Wilson suite is live-LLM tests — a full
run burns real API spend and wall-clock for coverage CI already owns. Run only targeted
paths (`NUM_RUNS=1 NODE_ENV=test bun test <path/to/file>`); pre-existing failures outside
your slice are not yours to chase.

Never run a production build — `bun run build`, `next build`, or a `vercel-build` stand-in.
The `vercel-build` check runs on draft PRs and owns that verdict. A local Next build peaked
at 12GB resident on 2026-08-27, exhausted swap, and starved every sibling lane. `bun
type-check` is the local compile gate: cheap, required before ship, and sufficient.

Checks run FOREGROUND. `bun type-check` (~15s warm, ~45s cold — measured 2026-09-01) and
scoped tests run as one plain foreground Bash command. Never `run_in_background`, never
`cmd | tail -N` — the backgrounded pipe can hang forever after the check finishes
(observed on this machine), and the spawn/poll scaffolding costs more wall-clock than the
check itself. Output too big → redirect to a file, then grep the file.

Enforced mechanically since 2026-09-01: lanes run with background Bash tasks disabled and
a 10-minute foreground timeout (`claude-lane` env), and the `tail-pipe-guard` PreToolUse
hook denies check commands piped into tail/head or backgrounded. A denied call means fix
the shape, not retry it.

Never kill build tools by a pattern match — one lane's `pkill -f "tsc --noEmit"` reaped its
siblings' in-flight checks on 2026-09-01 and forced their re-runs; kill only PIDs you spawned.

A rebase that replays cleanly with no new lane-authored code since your last green check
needs NO local re-verify — push immediately; CI's `pr-checks` runs the same type-check on
every push.

## Payload discipline

Context exhaustion — not difficulty — is why lanes hand off, and each handoff costs a full
respawn (brief + handoff re-read, ~20 min). Any command output that can exceed ~200 lines
goes to a FILE first (`> /tmp/<name>` or the scratchpad), then grep/head the file. Never
cat a store snapshot, fingerprint sweep, JSON dump, prod query result, or full test log
into context. `Read` big files with `offset`/`limit` after a grep, never whole.

## Subagents in a lane: never `fork`

A `fork` inherits the lane's entire context. On the AOA-4554 lane (2026-09-10) nine
parallel forks each started at 259K and ran to 484K–672K; one hit the 200-turn cap
mid-`git rebase` on the shared worktree, one ran the PR review loop the parent already
owned, and a nested fork was refused so that fork spawned 20 background agents instead.
Dispatch `general-purpose` / `Explore` / a layer specialist with a WRITTEN prompt that
carries the values it needs — never `subagent_type: "fork"`, never a `Workflow`. Parallel
agents on one worktree must own disjoint files; a shared file gets one agent, in sequence.
`WT_ULTRACODE` is off by default for the same reason: its "run a workflow for every task"
reminder is what licensed the fan-out, and its xhigh thinking is retained across the
lane's single mega-turn (~35% of context growth in the 3-day audit).

An Agent result reading `[Request interrupted by user for tool use]` or `The user doesn't
want to proceed with this tool use` means the subagent was KILLED, not that it declined:
Esc in the lane pane ends every in-flight subagent at once, and a subagent that calls
`TaskStop` on itself gets the same text. Its edits are already on disk in the shared
worktree with no summary. Run `git status` + `git diff --stat`, read what landed, and
continue from there — never re-dispatch the same work blind, and never `TaskStop` your own
id. `Agent terminated early due to an API error … session limit / weekly limit` is a 429:
`lane-pause.sh review 'rate limited until <reset time>'` and stop; retrying burns the
budget the limit exists to protect. A `NOTE: this agent stopped at its 200-turn limit`
result is PARTIAL — the task was too big for one agent; split it, do not resume it.

## Manual testing: the lane produces the evidence

The arbiter blocks any user-facing change without dev screenshots, and the lane makes them
itself — PR #8415 (ENGH-1392) cleared that gate with no human in the loop. The full
procedure is the repo's `docs/testing/playwright.md`; the shape:

1. Push, then `/host-dev` from the worktree → per-branch VM at
   `https://dev-env-<slug>.ngrok.app` that auto-pulls the branch. ~10 min the first time;
   a GCP `STOCKOUT` means retry later.
2. `bun run script -- generateDevEnvToken --userId <id> --orgId <id>` → 24h `token`
   cookie, dev secret pulled by the runner (no `.env.local`). The internal sandbox org
   and team-member user ids are in the repo's `docs/testing/playwright.md` — a real team
   member, so the admin UI unlocks.
3. Throwaway `_tmpScreenshot.mjs` at the worktree root, `import { chromium } from
   "playwright"`, cookie on the VM hostname, headless, screenshots into the scratchpad.
   Read every screenshot back. Delete the script; never commit it.
4. Images → parentless `evidence/<ticket>-manual-test-screenshots` branch
   (`hash-object` / `mktree` / `commit-tree`, push the sha), linked from the PR body with
   `?raw=true`. Never in the PR diff — that is a 🔴 on its own.
5. `gh pr edit --body-file` → the arbiter re-runs on `edited`; poll with one
   `devin-review.sh gate` call.

Never a local dev server, never the Playwright MCP (lanes have none), never a hand-rolled
token script. Anything verifiable over HTTP without a browser — chat API, a route — `curl`
it against the VM URL (`/test-feature`) and paste the output. A brief step that says
"local" means the dev env. Only a screen the procedure cannot reach (a third-party OAuth
page, a phone call) → `lane-pause.sh` `WAITING:input:<what>` with the URL in `## Local notes`.

## Pre-ship self-review (Opus gate)

Every lane runs this after its last slice is committed and BEFORE `/ship`. Why: external
reviewers hunt hardest on the first push, then anchor on verifying their own prior
findings — on PR #7448 a bug introduced by a fix commit (`selectedColumns` silent
narrowing) sailed past Devin, Greptile, and the arbiter, and a fresh-context "review this
diff for bugs" caught it. This gate is that fresh read, before the bots ever see the code.

The gate is bounded. PR #7619 ran 14 rounds (27 commits) because "exit on zero findings"
never terminates against a reviewer told to hunt: every fix is new surface, rounds 10–14
churned one defensive date-parsing branch, round 11 regressed, and the arbiter still
blocked on hygiene the loop never touched. Rounds measure patience, not quality.

**Hard cap: 3 rounds.** Round 1 reviews the whole branch; rounds 2–3 review only the fix
diff since the last reviewed sha. Anything still open after round 3 is recorded, not
fixed.

1. **Hygiene pre-check (before any reviewer).** Run the arbiter's own gates from
   `REVIEW.md` §PR hygiene against the diff: does it touch `src/schemas/**` or another
   persisted shape (→ `needs-human` is guaranteed; the PR body must tell the migration
   story)? Does it change a user-facing surface (→ screenshots required: produce them per
   §Manual testing and put them in the PR body at open time, not after the arbiter asks)?
   A persisted-shape change → write the finding into `## Local notes`, and `lane-pause.sh`
   with `WAITING:input:<what the human must supply>` right after the PR opens — do not
   spend review rounds polishing code that is blocked on evidence.
2. **Spawn ONE fresh-context reviewer running `/code-review`:** Agent tool,
   `subagent_type: "general-purpose"`, `model: "opus"` — never let it inherit the lane's
   sonnet. Its prompt: run the repo's `code-review` skill (`.claude/skills/code-review/
   SKILL.md`; a repo without one → `~/.claude/skills/code-review/SKILL.md`) in gate mode
   with the base (round 1: `origin/main`; later rounds: `--since <last reviewed sha>`),
   the round number, and the ticket's **Acceptance Criteria** and **Limitations**
   verbatim — scope is not justification, and without it the reviewer hunts defensive
   paths the ticket excludes. From round 2, also list the findings you claim to have
   fixed; it re-verifies each against the diff, never on your say-so. Give it NO lane
   history or justification of your choices: the skill reads the diff before any
   framing on purpose, and its Step 4 (new-surface ledger + two alternatives) is the
   part the bots never do. It returns a verdict with every finding tagged by kind
   (`[bug]` `[safety]` `[rule]` `[approach]`) and scope (`in-scope-blocking`,
   `in-scope-minor`, `out-of-scope`). Read-only — it must not edit or commit.
3. **Fix only `in-scope-blocking`.** Each fix starts with a failing test that reproduces
   the reviewer's scenario, then the change (`/tdd` applies to fix rounds exactly as to
   slices — round 11 of #7619 regressed two working date shapes because it skipped this).
   An `[approach]` finding is acted on in round 1 only — restructuring is cheapest
   before the PR exists and churn afterwards; in rounds 2–3 it is recorded, not fixed.
   `in-scope-minor` and `out-of-scope` go to `## Local notes` as one line each and into
   the PR body's Known limitations. Rejecting a blocking finding → one-line why in
   `## Local notes`; a rejected `[approach]` also names the alternative in the PR body,
   so the reviewer's comparison becomes the PR's "alternatives considered".
4. Record the round number in `<worktree>/.claude/preship-rounds` (a single integer,
   overwritten each round) and, at exit, a `Pre-ship review: N round(s)` line in the PR
   body Summary. Exit when a round returns zero `in-scope-blocking`, or after round 3.
5. Squash every fix commit into the slice commit it corrects before `/ship` (`git rebase
   -i` is unavailable; use `git reset --soft <slice-parent>` + recommit, or
   `git commit --fixup` + `GIT_SEQUENCE_EDITOR=true git rebase --autosquash`). A PR of
   27 "round N" commits gives Devin/Greptile a worse diff to review, not a better one.
   Never squash after the PR is open.
6. Then `/ship`.

Fix rounds during the review loop are the same blind spot: a fix commit is NEW surface
the bots won't re-hunt. Before pushing any fix round, run ONE gate pass scoped to the
unpushed work (`/code-review --since @{u}`) under the same tagging rule, fix what it
confirms as `in-scope-blocking`, then push. That single pass does not count toward the cap, and it
never spawns a second pass.

## Review loop (after `/ship`)

Roster state (verified 2026-08-10 late): **Devin's billing 402 outage is OVER** — the
trigger works again (proof: PR #6810, trigger → review in 3 min, arbiter consumed it).
**Macroscope is deprecated** (ENGH-509 / PR #6807 removes its config; it no longer reviews
new PRs — do not wait on `macroscopeapp[bot]`). Post-#6807, Greptile joins the roster and
Devin becomes mention-gated to high-blast-radius paths; the arbiter reads whatever
reviewers are present. The `arbiter` commit status remains the required gate throughout —
`pending — "waiting for reviewer output"` means no reviewer has posted on the head sha
yet, so make one fire.

1. **Request + wait — ONE tool call per round.** After the PR opens, and after EVERY
   subsequent push of fixes:

   ```bash
   git push && ~/.claude/scripts/devin-review.sh gate "https://github.com/{owner}/{repo}/pull/<PR>"
   ```

   `gate` does the whole round internally: triggers a Devin review if none covers the
   current head sha, polls to a terminal Devin status, then polls the arbiter commit
   status — sleeping inside the script, NOT across model turns. Exit 0 = arbiter
   `success`; 4 = timed out still pending (call `gate` once more, then `lane-pause.sh
   review` per stop condition 3); 5 = arbiter block (read + address findings); 6 =
   arbiter needs-human (read + address findings EXACTLY as for 5, push, gate once more,
   THEN report — see step 3). Exit 5 and 6 both mean step 2 runs; the only exit that
   skips step 2 is 0. NEVER hand-roll `status` + `sleep` as separate
   tool calls — every such poll is a full-context model turn spent reading "pending".
   The script handles auth internally — never source `.env.local` or handle the API key
   yourself. `402` from a bare `trigger` = billing relapse — never loop-retry;
   `lane-pause.sh review`, report. Making the gate inseparable from the push matters:
   a poll started before a push never covers the new sha.
2. **Read + address** — repo `REVIEW.md` is authoritative for severity markers: 🔴 (bug)
   and 🟨 (security) findings are blocking → fix EVERY one, inline comments included;
   🟡 = non-blocking, fix the ones that are cheap and clearly right. Fold Codex, Greptile
   (every P1/P2 inline comment), Devin, and the arbiter's own advisory notes into the same
   fix pass. Commit, run one self-review gate pass on the unpushed fix (§Pre-ship
   self-review), push, back to 1. A needs-human verdict does NOT skip this step: the
   human gate withholds the merge, it never withholds the fix pass. On PR #8431 the lane
   reported needs-human and stopped with five Greptile P1/P2 comments and four arbiter
   notes unread — that is the failure mode this sentence exists to prevent.
3. **Terminal** — the loop ends ONLY on: required `arbiter` commit status `success` on the
   final head sha with ZERO unaddressed blocking findings across all present reviewers —
   or an arbiter `needs-human` verdict on a head sha where every finding the lane CAN
   address is already addressed (→ report what remains for the human, then stop; a human
   must release it). The `needs-human-review` label is sticky across pushes and is never
   the signal — read the arbiter status description on the head sha. A new push resets
   arbiter to `pending`; check it on the FINAL sha:

   ```bash
   gh api repos/{owner}/{repo}/commits/<head-sha>/status \
     --jq '.statuses[] | select(.context=="arbiter")'
   ```

Chuck is RETIRED (2026-08-04): never tag `@chuck-noland-cartage`, never poll for a
`chuck-noland[bot]` comment.

## Stop conditions

Finish with `~/.claude/scripts/lane-done.sh` as the FINAL tool call (writes `DONE`, flashes
the lane's tmux window green). A lane stops ONLY on:

1. Zero unaddressed blocking findings from all present reviewers on the final sha — plus
   Arbiter `success` on that sha — + `lane-done.sh` run.
2. Genuine blocker: ambiguity not in the brief, repeated test failure on the same root
   cause, missing credential.
3. Arbiter `needs-human` on the final sha AFTER one full fix pass (every Greptile/Devin/
   arbiter finding addressed or rejected in `## Local notes`) — or no reviewer output
   ~15 min after a trigger round → `lane-pause.sh review 'PR #<N> review pending'`, stop
   without claiming done. A needs-human verdict with unread reviewer comments is never
   a stop.
4. Ctx nudge with a full slice still remaining → handoff (below).

## Ctx nudge + handoff

`lane-ctx-nudge.sh` (PostToolUse, non-blocking) injects a reminder at 260K/320K/380K ctx
(400K window). On nudge:

- **Review-only remainder** (one status poll + one feedback pass) → finish it +
  `lane-done.sh`. A review-only remainder NEVER justifies a handoff.
- **Full slice remaining** → wrap + commit, `/handoff`, then
  `~/.claude/scripts/lane-handoff.sh <doc>` as the FINAL tool call — wt-lanes' lane-run.sh
  respawns a fresh session that `/resume`s the doc and continues the brief, incl. any
  pending review loop. A `/handoff` without the `lane-handoff.sh` state write strands the
  lane: nothing respawns.
- Never compact in a lane.

## Spawning a fix/feedback lane from the cockpit (existing PR branch)

Used by `/address-feedback` and `/why-failing` after their plan is written:

```bash
[[ "$PWD" == */.claude/worktrees/* ]] && IN_LANE=1 || IN_LANE=0
# cockpit (IN_LANE=0): plan already at ~/.claude/plans/PR-<N>-<purpose>.md, then:
wt --branch <headRefName> PR-<N>-<purpose>
```

`wt`'s pre-spawn `git fetch origin` makes `origin/<headRefName>` available; `--branch`
checks out the real PR branch (and reuses a worktree that already holds it — no
double-checkout error). The `PR-<N>-*` pseudo-ticket plan filename is what makes `wt`
auto-kick-off the autonomous loop. Already in a lane (`IN_LANE=1`) → don't recurse;
continue inline.

## tmux: `wt` owns lane windows, and every call names its target

`wt` is the only thing that creates a lane window. Never hand-roll `tmux new-window` for a
lane, and never `nohup` one — a detached process has no pane and loses its scrollback.

`wt` spawns the window into the dedicated `wt` session and links it into whatever session
the user is attached to, so it appears in their cockpit without anyone asking. The window
lives in both at once, so `wt:<label>` stays its stable address. Opt out with `WT_NO_LINK=1`.
Do not move a lane window between sessions: `tmux move-window` breaks that address.

Every tmux call from an agent takes an explicit `-t <session>:<window-name>` target. The
Bash tool runs outside tmux, where an untargeted command resolves to the *user's* active
window — `tmux rename-window "x"` renames the window they are sitting in. Address windows
by name, never by index: closing a window renumbers the rest, so a stale index can land on
a live lane.

Never send Esc, Ctrl-C, or a keystroke into a lane pane while the lane is mid-turn: Esc
kills every in-flight subagent and hands the lane a bare `[Request interrupted…]` result
in place of each one's summary. Read the pane; if the lane must stop, `lane-pause.sh` it.

Slice protocol + parallel gotchas: `~/.dotfiles/CLAUDE.md`.
