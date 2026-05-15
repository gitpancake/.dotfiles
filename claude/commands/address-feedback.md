---
description: Pull PR review comments → triage → plan → spawn wt lane on PR branch.
argument-hint: <PR number or URL>
---

# /address-feedback $ARGUMENTS

Take an open PR, harvest every comment, triage into actionable feedback, write a plan at `~/.claude/plans/PR-<num>-feedback.md`, then spawn an autonomous `wt` lane **on the PR's own branch** so fixes land as follow-up commits. Planning + spawn only — do **not** edit project source from this command.

## 0. Parse arg

`$ARGUMENTS` = PR number or URL. Empty → ask and stop. Extract `PR_NUM`.

## 1. Fetch PR state (parallel)

- `gh pr view <PR_NUM> --json number,url,title,state,headRefName,baseRefName,author,isCrossRepository,body,comments,reviews`
- Inline review comments: `gh api repos/{owner}/{repo}/pulls/<PR_NUM>/comments --paginate` — path, line, diff hunk, body, author, `in_reply_to_id`.
- Review threads + resolved state: `gh api graphql` over `reviewThreads` → `isResolved`, `isOutdated`, thread comments.

**Stop conditions** (report, wait):
- PR not `OPEN` → refuse (merged/closed — nothing to push to).
- `isCrossRepository: true` (fork PR) → refuse: "fork PR — the head branch isn't on origin, so `wt --branch` can't check it out. Check out the fork manually." 
- No comments and no reviews → report "no feedback to address", stop.

## 2. Harvest — everything

Collect all comment surfaces, no pre-filter (`Comment scope: everything`):
- **Issue comments** (`comments`) — general PR discussion.
- **Review summaries** (`reviews[].body`) — includes the `@claude review` bot output.
- **Inline review comments** — each with `file:line` + diff hunk.

Tag each: author, source type, `resolved`/`outdated` state.

## 3. Triage

Classify every harvested comment:

| Class | Meaning | Goes to plan? |
|---|---|---|
| **actionable** | Concrete change requested — bug, missing guard, naming, test gap, perf | Yes — becomes a slice |
| **question** | Reviewer asked something; no change implied yet | Open questions — lane answers in the final report, never guesses in-thread |
| **skip** | Praise, already-resolved, outdated, acknowledged nit, off-topic | Listed under Skipped with a one-line reason |

Resolved/outdated threads default to **skip** unless the body still names an unaddressed change — state the call either way.

## 4. Surface area

For each **actionable** item, grep the named `file:line`. List the top files to read first, one-line reason each. Note cross-file blast radius.

## 5. Write plan — `~/.claude/plans/PR-<PR_NUM>-feedback.md`

≤200 lines. Heading: `# PR-<PR_NUM>-feedback — <pr title>`. Sections:

- **PR** — url, head branch (`headRefName`), base branch.
- **Feedback triaged** — the §3 table. Actionable items numbered; skipped items with reason; questions listed.
- **Slices** — one slice per actionable item (group by file/layer when they overlap). Each: what changes, `file:line`, why safe to merge. No flip pattern — these are follow-up commits to an already-open PR.
- **Open questions** — the `question`-class comments. Lane answers them in its final report, not in the PR thread.
- **Branch + worktree** — branch = `headRefName` (existing, do not create); worktree = `<repo>/.claude/worktrees/pr-<PR_NUM>-feedback`.
- **Done when** — every actionable item committed + pushed to the PR branch, `/ship <PR_NUM>` re-review run, questions answered in the report.

The plan filename uses pseudo-ticket `PR-<PR_NUM>` so `wt` treats the slug as ticket-shaped and auto-kicks-off the autonomous loop.

## 6. Coverage self-check

Confirm every **actionable** row in §3 maps to a slice in §5. Any unmapped → fix the plan before spawning. (No `plan-lint` here — that gate compares against a ticket brief; this plan is PR-driven.)

## 7. Spawn the lane

Detect lane:

```bash
[[ "$PWD" == */.claude/worktrees/* ]] && IN_LANE=1 || IN_LANE=0
```

### Cockpit (`IN_LANE=0`)

**You MUST run this via the Bash tool** — it opens a new tmux window with claude in autonomous mode:

```bash
wt --branch <headRefName> PR-<PR_NUM>-feedback
```

`wt`'s pre-spawn `git fetch origin` makes `origin/<headRefName>` available; `--branch` checks the real PR branch into the worktree (DWIM tracking branch). If that branch is already checked out in an existing worktree (e.g. a still-open lane from when the PR was built), `wt` reuses that worktree instead of erroring on a double checkout. The plan already exists at `~/.claude/plans/PR-<PR_NUM>-feedback.md`, so `wt` auto-kicks-off the autonomous loop. Then stop:

> Lane spawned on PR #<PR_NUM>'s branch. Autonomous feedback loop running in new tmux window. This pane is done.

### Inside a lane (`IN_LANE=1`)

Don't recurse. Continue inline:

> Plan ready. Beginning autonomous feedback implementation. Commits push to the PR branch; `/ship <PR_NUM>` at end for re-review.

Read the plan, implement each slice end-to-end (type-check + tests per slice, commit per logical fix), push to the PR's head branch, run `/ship <PR_NUM>` for a review-only re-review, and answer the open questions in the final report. Stop only on: PR pushed + re-review run, or a genuine blocker (ambiguity not in the plan, repeated test failure on the same root cause, missing credential).
