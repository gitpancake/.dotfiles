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

## Payload discipline

Context exhaustion — not difficulty — is why lanes hand off, and each handoff costs a full
respawn (brief + handoff re-read, ~20 min). Any command output that can exceed ~200 lines
goes to a FILE first (`> /tmp/<name>` or the scratchpad), then grep/head the file. Never
cat a store snapshot, fingerprint sweep, JSON dump, prod query result, or full test log
into context. `Read` big files with `offset`/`limit` after a grep, never whole.

## Pre-ship self-review (Opus gate)

Every lane runs this after its last slice is committed and BEFORE `/ship`. Why: external
reviewers hunt hardest on the first push, then anchor on verifying their own prior
findings — on PR #7448 a bug introduced by a fix commit (`selectedColumns` silent
narrowing) sailed past Devin, Greptile, and the arbiter, and a fresh-context "review this
diff for bugs" caught it. This gate is that fresh read, before the bots ever see the code.

1. Spawn ONE fresh-context reviewer: Agent tool, `subagent_type: "general-purpose"`,
   `model: "opus"` — never let it inherit the lane's sonnet. Give it NO lane history or
   justification of your choices. Prompt: run `git diff origin/main...HEAD` (plus bare
   `git diff` for anything uncommitted) and adversarially hunt for bugs — logic errors,
   silent-failure paths, unvalidated model/user input, races, wrong-but-plausible edge
   cases. Report only real bugs, each with `file:line` and a concrete failure scenario
   (inputs → wrong outcome). No style, naming, or test-coverage feedback. Read-only —
   it must not edit or commit.
2. Fix every confirmed finding, commit, spawn a fresh pass. Exit when a pass returns
   zero confirmed bugs. Rejecting a finding → one-line why in `## Local notes`.
3. Then `/ship`.

Fix rounds are the same blind spot: a fix commit is NEW surface the bots won't re-hunt.
During the review loop below, before pushing any fix round, run one gate pass scoped to
the unpushed work (`git diff @{u}`), fix what it confirms, then push.

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
   review` per stop condition 3); 5 = arbiter failure (read + address findings); 6 =
   needs-human-review (stop and report). NEVER hand-roll `status` + `sleep` as separate
   tool calls — every such poll is a full-context model turn spent reading "pending".
   The script handles auth internally — never source `.env.local` or handle the API key
   yourself. `402` from a bare `trigger` = billing relapse — never loop-retry;
   `lane-pause.sh review`, report. Making the gate inseparable from the push matters:
   a poll started before a push never covers the new sha.
2. **Read + address** — repo `REVIEW.md` is authoritative for severity markers: 🔴 (bug)
   and 🟨 (security) findings are blocking → fix EVERY one, inline comments included;
   🟡 = non-blocking, fix the ones that are cheap and clearly right. Fold Codex, Greptile,
   and any other bot reviews on the PR into the same fix pass. Commit, run one self-review
   gate pass on the unpushed fix (§Pre-ship self-review), push, back to 1.
3. **Terminal** — the loop ends ONLY on: required `arbiter` commit status `success` on the
   final head sha with ZERO unaddressed blocking findings across all present reviewers —
   or the `needs-human-review` label / a `NEEDS-HUMAN-REVIEW` verdict landing (→ stop and
   report; a human must release it). A new push resets arbiter to `pending`; check it on
   the FINAL sha:

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
3. `needs-human-review` label applied — or no reviewer output ~15 min after a trigger
   round → `lane-pause.sh review 'PR #<N> review pending'`, stop without claiming done.
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

Slice protocol + parallel gotchas: `~/.dotfiles/CLAUDE.md`.
