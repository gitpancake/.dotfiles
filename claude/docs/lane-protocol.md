# Lane Protocol — autonomous `wt` lanes

Single source of truth for the lane lifecycle: spawn → slices → `/ship` → review loop →
done/handoff. Referenced by global CLAUDE.md and `/ship`, `/address-feedback`,
`/why-failing`, `/resume`. Read this when working in a lane (cwd under
`<repo>/.claude/worktrees/`) or spawning one.

## Semantics

`wt` = fire-and-forget. The lane owns its work end-to-end: read the brief, plan slices,
`/tdd` for behavior-changing slices, commit per layer, `/ship`, then the review loop below.
Feedback is NEVER deferred to a separate lane.

## Review loop (after `/ship`)

Every lane runs the **Devin loop** on its PR — request, poll, address, repeat:

1. **Request** — after the PR opens, and after EVERY subsequent push of fixes, comment on
   the PR: `@devin-ai-integration please review this PR`.
2. **Poll** — Devin (`devin-ai-integration[bot]`) posts a normal GitHub Review object with
   inline comments (`pulls/<PR>/comments`). Poll its latest review:

   ```bash
   gh api repos/{owner}/{repo}/pulls/<PR>/reviews \
     --jq '[.[] | select(.user.login=="devin-ai-integration[bot]")] | last | "\(.state) @ \(.commit_id)"'
   ```

   `sleep 90` between checks, up to 10 attempts (~15 min) per round.
3. **Address** — latest Devin review not APPROVED on the current head sha → fix EVERY
   finding (inline comments included), commit, push, go to 1.
4. **Terminal** — the loop ends ONLY on: Devin review state `APPROVED` on the current head
   sha, or the `needs-human-review` label landing on the PR (→ stop and report; a human
   must release it).

Codex reviews arrive automatically alongside — fold its inline comments into the same fix
pass. **Arbiter** (`.github/workflows/arbiter.yml`, where present — e.g. `cartage-agent`,
ENGH-250) synthesizes reviewer output + diff + CI into a REQUIRED `arbiter` commit status
(`approve`=success, `block`/`needs-human`=failure) plus an issue comment from
`github-actions[bot]` starting `<!-- arbiter-verdict -->`; a new push resets it to
`pending`. Where it exists, `arbiter=success` on the final sha is ALSO required before the
lane is done:

```bash
gh api repos/{owner}/{repo}/commits/<head-sha>/status --jq '.statuses[] | select(.context=="arbiter")'
```

Chuck is RETIRED (2026-08-04): never tag `@chuck-noland-cartage`, never poll for a
`chuck-noland[bot]` comment.

## Stop conditions

Finish with `~/.claude/scripts/lane-done.sh` as the FINAL tool call (writes `DONE`, flashes
the lane's tmux window green). A lane stops ONLY on:

1. Devin `APPROVED` on the final sha — plus Arbiter `approve` where `arbiter.yml` exists —
   + `lane-done.sh` run.
2. Genuine blocker: ambiguity not in the brief, repeated test failure on the same root
   cause, missing credential.
3. `needs-human-review` label applied — or Devin review still absent ~15 min after a
   request round → `lane-pause.sh review 'PR #<N> review pending'`, stop without claiming
   done.
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
tmux rename-window "<purpose>:PR-<N>"
```

`wt`'s pre-spawn `git fetch origin` makes `origin/<headRefName>` available; `--branch`
checks out the real PR branch (and reuses a worktree that already holds it — no
double-checkout error). The `PR-<N>-*` pseudo-ticket plan filename is what makes `wt`
auto-kick-off the autonomous loop. Already in a lane (`IN_LANE=1`) → don't recurse;
continue inline.

Slice protocol + parallel gotchas: `~/.dotfiles/CLAUDE.md`.
