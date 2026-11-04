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
check itself. Output too big → redirect to a file, then grep the file. The one
backgrounded command in a lane is the review gate (§Review loop step 1): it waits on
remote reviewers for minutes, spawns nothing, and must not freeze the lane.

Enforced mechanically since 2026-09-01: lanes run with background Bash tasks disabled and
a 10-minute foreground timeout (`claude-lane` env), and the `tail-pipe-guard` PreToolUse
hook denies any app process (`bun run script`, `bun test`, `node`, …) piped into tail/head,
checks backgrounded, and `tail -f` anywhere (it never exits; poll a file with `tail -n 40`
in a bounded loop). A denied call means fix the shape, not retry it.

Never kill build tools by a pattern match — one lane's `pkill -f "tsc --noEmit"` reaped its
siblings' in-flight checks on 2026-09-01 and forced their re-runs; kill only PIDs you spawned.

A rebase or merge of main, conflicts resolved or not, needs NO local re-verify before the
push — push immediately with `--force-with-lease` (plain `git push` after a merge); CI's
`pr-checks` runs the same type-check on every push.

A lane's HEAD is its own branch, never `main`. The `main` ref is shared with the cockpit
and every sibling worktree: `git checkout main` in a lane parks it here, blocks checkout
everywhere else, and makes the next commit a commit on main (users-flip, 2026-11-04, did
this to rerun a backfill against "PR1's merged state"). The `lane-main-guard` hook denies
`git checkout|switch main` in a lane. Need main's content? `git show origin/main:<path>`,
`git diff origin/main -- <path>`, or `git worktree add <scratch> --detach origin/main`.

## Dependencies are shared, read-only

`wt` links each lane's `node_modules` to the cockpit checkout's (`deps: linked -> …` on
spawn). One tree serves every lane, so a lane that changes it changes it for all of them.
Never run `bun install`, `bun add`, `bun remove`, `node-gyp`, a native-module rebuild, or
`rm -rf node_modules/<pkg>` from a lane, and never `cd` into the cockpit checkout to do it
there. A dependency change is a commit to `package.json` + `bun.lock` on your branch; the
cockpit installs it, once, when that merges.

A native module that crashes on load is not sibling contention and is not yours to rebuild.
On 2026-11-04 one lane reinstalled `re2` and another rebuilt it with `node-gyp`; the
source-built `re2.node` segfaulted Bun 1.3.9 and 1.3.13 on load and took down the prod
backfill dry-run and two unrelated lanes until the cockpit removed it. `re2` is an untrusted
optional peer (not in `trustedDependencies`), so a clean install never builds it and
`email-reply-parser` / `superstatic` fall back to JS regex when `require("re2")` throws.
Stop, say `native module crash: <module>` in your summary, and let the cockpit fix the
shared tree.

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
`lane-pause.sh external 'rate limited until <reset time>'` and stop; retrying burns the
budget the limit exists to protect. A `NOTE: this agent stopped at its 200-turn limit`
result is PARTIAL — the task was too big for one agent; split it, do not resume it.

## Manual testing: the lane produces the evidence

The brief's **Proof → Manual Tests** are the lane's to run — every step, before `/ship`.
The PR body carries the evidence and the "performed on dev" checkbox is ticked only when
they ran. "Needs a human on dev" is never a ship-time caveat: a step the lane truly cannot
reach pauses the lane (`WAITING:input`, below) BEFORE `/ship`, and everything else runs.
PR #9137 (ENGH-1881) shipped with "both steps need a human"; told to do them itself, the
lane had the VM up, the token minted and a whitelist test number found in four minutes —
the capability was never missing, only the decision. PR #8415 (ENGH-1392) cleared the
arbiter's manual-testing gate with no human in the loop. The full procedure is the repo's
`docs/testing/playwright.md`; the shape:

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
4. Evidence goes in the PR body itself, uploaded with GitHub's own attach: the repo's
   `/manual-test` §5. `pr-body.md` sits in the same folder as the PNGs, each step
   references its screenshot as `![alt](01-step.png)`, and `--body-file` plus every
   `--attach` go in ONE `gh pr edit` call. `--attach` rewires only a reference whose
   path resolves to the attached file; anything else stays a broken image and the upload
   lands as an orphan at the bottom (PRs #10142–#10178, 2026-10-27), and the hook and the
   arbiter now count that as missing evidence. NEVER an `evidence/*` branch, never a
   blob link into the repo, never an image in the PR diff — the arbiter blocks all
   three, and a lane that pushed one cannot recover (PR #9118 ended in a self-override
   that paged a maintainer). Next to each screenshot, paste the outcome as text a reader
   can check: the API response, the dev Postgres row, the rendered message. Without a
   `gh` that has `--attach` (≥ 2.99.0), the pasted outcome is the evidence, the PNGs are
   handed to a session or person who can upload them, and the PR is not marked ready.
5. `gh pr edit --body-file` → the arbiter re-runs on `edited`; poll with one
   `devin-review.sh gate` call.

Never a local dev server, never the Playwright MCP (lanes have none), never a hand-rolled
token script. Anything verifiable over HTTP without a browser — chat API, a route — `curl`
it against the VM URL (`/test-feature`) and paste the output. A brief step that says
"local" means the dev env. Slack, Teams, Google Chat, SMS and email steps are NOT
exemptions: drive the channel through the dev org's test channel or a synthetic ingress
event, verify a send or a denial through the outbound row in dev Postgres, and paste the
query rows. "No SMS arrives" is a `denied` row against the whitelist's 555 test number,
not a handset. The only exemption is a screen no script can reach — a third-party OAuth
consent page, a live voice call — and that is `lane-pause.sh` `WAITING:input:<what>` with
the URL in `## Local notes`, before `/ship`, never a note in the PR body.

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

0. **Mechanical gates (before any reviewer, and again before every push).** Run the same
   deterministic checks CI runs, foreground, and fix every red before round 1 starts.
   Since 2026-11-04 a `pre-push` git hook (`~/.wt-lanes/hooks/pre-push`, installed by
   `wt` into the repo's `.git/hooks`) runs those guards itself and refuses the push
   when one is red, printing the failed guards. A refused push is a guard failure to
   fix and commit, never a reason to retry, set `WT_SKIP_GUARDS`, or push from
   elsewhere; the hook takes ~5s (it skips `credless-test-hermetic`, a hang detector
   CI still runs). In
   cartage-agent that is `bun run gates/prChecks/runGuards.ts` (every `check:*` guard —
   boolean-naming, prettier, ring violations, pr-body-claims, migration rules — each falls
   back to the merge-base with `origin/main` when its `*_BASE_SHA` env is unset), then
   `bun type-check`, `bun run lint`, and the unit tests scoped to the touched paths. Another
   repo → whatever its `.github/workflows/` runs under `pr-checks`. On 2026-10-27 all seven
   open lane PRs were red on first push, every failure a guard that would have failed
   locally in under five minutes; each push re-fires Arbiter, Devin and Greptile, so a
   red first push costs a full review round, not a retry.
1. **Hygiene pre-check (before any reviewer).** Run the arbiter's own gates from
   `REVIEW.md` §PR hygiene against the diff: does it touch `src/schemas/**` or another
   persisted shape (→ `needs-human` is guaranteed; the PR body must tell the migration
   story)? Does it change a user-facing surface (→ screenshots required: produce them per
   §Manual testing and put them in the PR body at open time, not after the arbiter asks)?
   Does the brief's Proof list manual tests (→ every one ran, evidence pasted in the body,
   checkbox ticked — a PR is not ready with any of them "not done")?
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
the bots won't re-hunt. Before pushing any fix round, run the mechanical gates (step 0)
and then ONE gate pass scoped to the unpushed work (`/code-review --since @{u}`) under the
same tagging rule, fix what it confirms as `in-scope-blocking`, then push. That single pass does not count toward the cap, and it
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

0. **Gate check — repo has `arbiter.yml`? Check BEFORE triggering anything.** Run
   `test -f .github/workflows/arbiter.yml` (or `ls .github/workflows/ | grep -i arbiter`)
   in the worktree first. Missing → this repo has no arbiter gate; skip the entire
   review loop below, note "no reviews on this repo" in the report, and go straight to
   `lane-done.sh`. This check is a plain, instant `Bash`/`Read` call — never spend a
   `Monitor`-wrapped `devin-review.sh gate` round finding this out; that burns up to
   ~9 min discovering what a file-existence check answers in milliseconds (PR #1518,
   ai-employees — no `arbiter.yml` in that repo, caught only after a gate round had
   already been armed).

1. **Request + wait — ONE tool call per round.** After the PR opens, and after EVERY
   subsequent push of fixes:

   ```bash
   git push && ~/.claude/scripts/devin-review.sh gate "https://github.com/{owner}/{repo}/pull/<PR>"
   ```

   Run it through the **Monitor** tool (load it with `ToolSearch("select:Monitor")`):
   `cd <worktree> && git push && ~/.claude/scripts/devin-review.sh gate "<PR url>"; echo
   GATE_EXIT=$?` with `timeout_ms: 900000`. A lane's Bash tool has no `run_in_background`
   — `claude-lane` disables background tasks, so passing it fails with
   `InputValidationError` (43 of 43 attempts, 09-26 → 10-01) — and the guard hook denies
   a foreground Bash `gate`, because it would freeze the lane for up to ~9 min. Under
   Monitor the lane stays reachable, each poll line arrives as an event, and the last
   line carries the exit code. It is still ONE tool call — do not start a second one or
   poll beside it. `gate` does the whole round internally:
   triggers a Devin review if none covers the current head sha, then waits for a
   SETTLED arbiter verdict — sleeping inside the script, NOT across model turns. Settled means the `arbiter` status on the head sha is
   newer than every reviewer post on that sha and unchanged across two polls. This is
   the whole point: the arbiter posts a verdict on every push BEFORE any reviewer has
   read the sha and re-runs 3-5 min after each reviewer round, so the first terminal
   status is stale (PR #8665: push-time block 03:01:00, Devin 03:02:21, Greptile
   03:02:35, real verdict 03:06:44 — a lane reading the first one fixed the wrong list
   and never saw Devin's or Greptile's findings until they were pasted in by hand).
   On exit `gate` prints summary JSON, then EVERY finding on the head sha — the
   arbiter verdict comment, each reviewer's review body, each inline comment still
   applying — and mirrors them to `<lane>/.claude/review-findings.md`. That printout
   IS step 2's input; nothing else needs fetching. `devin-review.sh findings <PR-url>`
   re-prints it without waiting. Exit 0 = arbiter `success`; 4 = unsettled/pending
   after the window (call `gate` once more, then `lane-pause.sh review` per stop
   condition 3); 5 = arbiter block; 6 = arbiter needs-human and 8 = arbiter
   needs-holland (address findings EXACTLY as for 5, push, gate once more, THEN pause
   on the hold — see step 3); 9 = arbiter success but `prompt-owner-review` is
   awaiting an owner (`lane-pause.sh prompt-owner 'PR #<N> awaiting <owners>'`);
   10 = CI is red on the head sha — a GitHub Actions check-run (`pr-checks`, `guards`,
   `PG Migration Check`, …) concluded failure, whatever the arbiter said. The printout
   ends with a `### CI failures` section carrying each failed job's `##[error]` lines
   (e.g. `2 guard(s) failed: boolean-naming, prettier`). Fix those AND every arbiter
   finding in the same push, run `bun run gates/prChecks/runGuards.ts` locally first,
   then gate once more. `gate` never exits 0 while `pr-checks` is queued or running,
   and the arbiter never reads CI, so arbiter `success` on a red sha is normal and is
   not done (PR #10460: arbiter success 21:56, guards red 21:58, lane-done 22:03).
   Exits 5, 6, 8 and 10 all mean step 2 runs; the only exits that skip step 2 are 0 and 9. `devin-review.sh status|trigger|
   wait`, `sleep N &&` polls, and loops over `commits/<sha>/status` are DENIED in lanes
   by `~/.claude/hooks/review-gate-guard.sh` — a denial means use `gate`, not a retry.
   The script handles auth internally — never source `.env.local` or handle the API key
   yourself. `402` from a bare `trigger` = billing relapse — never loop-retry;
   `lane-pause.sh review`, report. Making the gate inseparable from the push matters:
   a poll started before a push never covers the new sha.
2. **Judge, then address** — the findings `gate` printed. READ every one: Codex, Greptile
   (every P1/P2 inline comment), Devin, and the arbiter's own advisory notes. Repo
   `REVIEW.md` is authoritative for severity markers: 🔴 (bug) and 🟨 (security) are
   blocking, 🟡 is not. Give each finding a verdict before touching code: **valid** (you
   can state the input that breaks), **invalid** (one line of evidence), or **design
   change** (it asks for a new field on a persisted shape, a new abstraction, or a changed
   contract). A reviewer is not smarter than the brief — on four PRs reviewed 2026-09-15
   every finding was accepted as true and fixed at once, and many later findings were
   real bugs those fixes introduced. Fix every valid blocking finding, each with a
   failing test first, and the valid 🟡 ones that are cheap and clearly right. Record
   the invalid ones in `## Local notes` with their evidence. A design change is not the
   lane's call: `lane-pause.sh` with `WAITING:input:<the choice>` and stop. Commit, run
   one self-review gate pass on the unpushed fix (§Pre-ship self-review), push, back to
   1. A needs-human or needs-holland verdict does NOT skip this step: the hold withholds the merge,
   it never withholds the judging and the fix pass. On PR #8431 the lane reported
   needs-human and stopped with five Greptile P1/P2 comments and four arbiter notes
   unread — that is the failure mode this sentence exists to prevent.
   **Two rounds, then brake.** If the second post-ship fix round does not reach arbiter
   `success`, do not start a third. `lane-pause.sh review` with one paragraph in
   `## Local notes` on why it is circling — which findings keep returning and what each
   fix changed. Rounds past two measure patience, not quality.
3. **Terminal** — the loop ends on: required `arbiter` commit status `success` on the
   final head sha with ZERO unjudged findings and ZERO unfixed valid blocking findings
   across all present reviewers — or the two-round brake — or a design-change pause —
   or an arbiter `needs-human` verdict on a head sha where every finding the lane CAN
   address is already addressed (→ report what remains for the human, then stop; a human
   must release it). The `needs-human-review` label is sticky across pushes and is never
   the signal — read the arbiter status description on the head sha. A new push resets
   arbiter to `pending`; check it on the FINAL sha:

   ```bash
   gh api repos/{owner}/{repo}/commits/<head-sha>/status \
     --jq '.statuses[] | select(.context=="arbiter")'
   ```

   **`needs-holland` is a conversation, not a wait.** The arbiter's verdict carries "The
   question for Holland:". Holland March (`@holland-march-cartage`) takes the case within
   ~10 minutes and posts his review and his question to the author in Slack
   `#eng-pull-requests`, one thread per PR, which a lane cannot read. So the lane answers the
   arbiter's question itself, at once, as a PR comment that starts with
   `@holland-march-cartage`: the decision, the evidence (file:line, test names, run ids),
   and what trade-off it accepts. Holland's GitHub webhook opens or continues the case on
   that mention and he closes it as `unblock` from the PR. Then
   `lane-pause.sh holland 'PR #<N>: <the question> — answered at <comment url>'`: the tab
   blinks purple and the cockpit's hold watcher (`lane-holds.sh`) marks the lane done when
   Holland unblocks, or red when he posts findings. The detail names the question and
   links the answer, never "awaiting Holland", and a lane never keeps gating a hold. On
   2026-11-01 three PRs sat six hours because each lane paused on "awaiting Holland" while
   his question sat unread in Slack.

Chuck is RETIRED (2026-08-04): never tag `@chuck-noland-cartage`, never poll for a
`chuck-noland[bot]` comment.

### Owner gates (cartage-agent): the runtime one is ours to release

Three required commit statuses sit beside `arbiter` and hold a PR on a human roster, not
on findings: `wilson-runtime-owner-review` (`src/server/agents/WilsonV3/runtime/**`,
`gates/ownerGate/**`, `gates/wilsonRuntimeOwner/**`), `prompt-owner-review`
(prompts/knowledge, `*.prompts.ts`), `wallet-owner-review` (cartage-pay, bills, wallet).
`failure`/`pending` on one of these is never a findings loop — there is nothing to fix —
and `override-devin-gate` releases none of them.

**Henry (`gitpancake`) is on the `wilson-runtime-owner-review` roster, and the lane's `gh`
runs as him** (`gh api user --jq .login` → `gitpancake`). That gate is never a human
blocker for a lane and never goes in a pause message as "awaiting @gitpancake". It is
released by the lane, mechanically: `devin-review.sh gate` does it itself the moment the
arbiter settles `success` on the head sha (remove + re-add `wilson-runtime-owner-override`,
then wait for the status to flip; exit 7 if it does not). A red
`wilson-runtime-owner-review` while the arbiter is still blocked is simply pending — fix
the arbiter's findings first, because any later push re-raises the gate and a label granted
on an earlier commit is a stale override it rejects (`override was for an earlier commit —
remove and re-apply`). To release a head that is already final without a full gate round:

```bash
~/.claude/scripts/devin-review.sh release-runtime-gate "https://github.com/{owner}/{repo}/pull/<PR>"
```

Never approve the PR as a release (the lane's author is the PR author, and GitHub refuses
self-approval).

`prompt-owner-review` and `wallet-owner-review` stay human-held (their rosters live in the
repo's gate workflows under `.github/workflows/` and `gates/`): report which one is red and
stop, never report the PR as clean, never apply their override labels — each gate checks
the labeler's login against its roster, so a non-owner add is a no-op (`last applied by someone off the owner roster`).

## Stop conditions

Every stop ends in exactly ONE of three final tool calls: `~/.claude/scripts/lane-done.sh`
(writes `DONE`, flashes the tab green), `~/.claude/scripts/lane-pause.sh <code> '<detail>'`
(codes in `~/.claude/agent-state-vocab.md`), or `~/.claude/scripts/lane-handoff.sh <doc>`.
A turn that ends with none of them shows on the cockpit as `stopped without a pause code`,
red, and counts as a breach. A lane stops ONLY on:

1. Every finding from all present reviewers on the final sha judged, every valid blocking
   one fixed — plus Arbiter `success` on that sha — plus every CI check-run on that sha
   green (`gate` exit 0 asserts both; `lane-done.sh` refuses a red head) — plus
   `wilson-runtime-owner-review` self-released on that sha when the PR touches runtime
   paths — + `lane-done.sh` run.
2. Genuine blocker: ambiguity not in the brief (`ambiguity`), repeated test failure on the
   same root cause (`test-loop`), missing credential (`creds`), a reviewer finding that is
   a design change (`input`), or two post-ship fix rounds without arbiter `success`
   (`review`, never a third round).
3. A hold on the final sha AFTER one full fix pass (every Greptile/Devin/arbiter finding
   fixed or rejected with evidence in `## Local notes`): `needs-human` → `human`,
   `needs-holland` → `holland` (after the answer comment), `prompt-owner-review`
   awaiting an owner → `prompt-owner`. The tab blinks purple; the cockpit's hold watcher
   marks the lane done when the person releases it. A hold verdict with unread reviewer
   comments is never a stop.
4. No reviewer output ~15 min after a trigger round, or the gate still unsettled after a
   second call → `lane-pause.sh review 'PR #<N> review pending'`, without claiming done.
5. Ctx nudge with a full slice still remaining → handoff (below).

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
