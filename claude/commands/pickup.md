---
description: Pick up a local ticket brief — sync the cockpit to a base branch, fold in any extra context, then spawn an autonomous wt lane.
argument-hint: <TICKET> <BASE-BRANCH> [extra context...]
---

# /pickup $ARGUMENTS

Wraps `wt` for the common pickup: take a brief at `~/.claude/tickets/**/<TICKET>.md`, sync the
cockpit to a base branch, fold in any extra context, spawn the lane. Do **not** edit project
source — this command only prepares and spawns.

## 1. Parse

`$ARGUMENTS` = `<TICKET> <BASE> [context...]`:
- **token 1** — `TICKET` (required). Linear-style ID or `DRAFT-<N>`. Empty → ask, stop.
- **token 2** — `BASE` (required). Base branch to spawn off. `.` = use the cockpit's
  current branch as-is.
- **rest** — `CONTEXT` (optional). Free-text notes for the lane.

## 2. Locate the brief

`find ~/.claude/tickets -name "<TICKET>.md" -type f` → `BRIEF`.
- **Not found** → stop. Tell user: `/sync-from-linear` (real Linear ticket) or `/scope`
  (fresh idea) first.

## 3. Fold in context — only if `CONTEXT` non-empty

Append to `BRIEF` under `## Local notes` (create that section at end of file if missing):

```
### Pickup note — <ISO-8601 date>
<CONTEXT>
```

It rides with the brief — the lane reads it, and it survives `/handoff`.

## 4. Sync the cockpit to BASE

Skip if `BASE` == `.`.

```bash
git fetch --quiet origin
git rev-parse --verify "origin/<BASE>"   # missing → stop, report
git checkout "<BASE>"
git merge --ff-only "origin/<BASE>"
```

ff-merge fails (dirty tree / diverged) → stop, surface it. Never force.

## 5. Spawn the lane

Run via the Bash tool — it opens a new tmux window with claude in autonomous mode:

```bash
wt <TICKET>
```

`wt` branches off the now-current `BASE`, creates the worktree + per-lane port, and the lane
reads `BRIEF` as its brief. Branch type defaults to `feature/` — for a `fix/` or `refactor/`
lane, run `wt --type <prefix> <TICKET>` directly instead.

Report, then stop:

> Lane spawned off `<BASE>`. Autonomous dev loop running in new tmux window. This pane is done.

## Stop conditions

- Missing `TICKET` / `BASE`, or brief not found — ask or report, stop.
- ff-merge failure — surface, stop.
- After spawn — done. Don't follow the lane.
