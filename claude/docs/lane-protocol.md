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

Reviews fire **automatically** on PR open/push — nothing to tag or trigger, and pushing new
commits IS the re-review request (there is no re-review command; `/ship` takes no part in it).
Chuck is RETIRED (2026-08-04): never tag `@chuck-noland-cartage`, never poll for a
`chuck-noland[bot]` comment.

- **Devin** (`devin-ai-integration[bot]`) + **Codex** post normal GitHub Review objects with
  inline comments (`pulls/<PR>/comments`).
- **Arbiter** (`.github/workflows/arbiter.yml`, where present — e.g. `cartage-agent`, ENGH-250)
  synthesizes reviewer output + diff + CI into a REQUIRED `arbiter` commit status
  (`approve`=success, `block`/`needs-human`=failure) plus an issue comment from
  `github-actions[bot]` starting `<!-- arbiter-verdict -->`, stamped with the head sha it
  judged. A new push resets the verdict to `pending` and re-reviews automatically.

Poll the head sha:

```bash
gh api repos/{owner}/{repo}/commits/<head-sha>/status --jq '.statuses[] | select(.context=="arbiter")'
```

- `block` → address the Arbiter blocking findings + Devin/Codex inline comments, commit +
  push, poll again.
- `needs-human` → the `needs-human-review` label is applied — stop and report; a human must
  release it.

## Stop conditions

Finish with `~/.claude/scripts/lane-done.sh` as the FINAL tool call (writes `DONE`, flashes
the lane's tmux window green). A lane stops ONLY on:

1. Arbiter `approve` on the final sha (repo without `arbiter.yml` → PR opened) +
   `lane-done.sh` run.
2. Genuine blocker: ambiguity not in the brief, repeated test failure on the same root
   cause, missing credential.
3. `needs-human` verdict — or verdict still `pending` ~15 min after CI settles →
   `lane-pause.sh review 'PR #<N> review pending'`, stop without claiming done.
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
