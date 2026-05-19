---
description: Pickup epic — confirm story list, spawn Ralph lane.
argument-hint: <EPIC> <BASE-BRANCH> [extra context...]
---

# /epic $ARGUMENTS

Spawns `wt --ralph` — a lane running the Ralph autonomous loop over an epic.

An **epic** is a folder with an `_epic.md` at its root — the durable, Ralph-ready PRD
(contract: `$TICKETS_DIR/README.md`). `_epic.md` carries the `<!-- epic-stories:start -->`
block: the authoritative ordered story list + dependency DAG. `/epic` confirms that order with
the user, then spawns the lane. The lane runs `epic-parse.sh` to project `_epic.md` into
`scripts/ralph/prd.json` and executes it — **Ralph never decomposes; it executes a confirmed
list.** There is one epic shape. No `.epics.json`, no in-lane `/prd` + `/ralph` synthesis.

Syncs the cockpit to a base branch, folds in any extra context, spawns the lane. Do **not**
edit project source — this command only prepares and spawns.

## 1. Parse

`$ARGUMENTS` = `<EPIC> <BASE> [context...]`:
- **token 1** — `EPIC` (required). An epic folder slug, a Linear epic id, or an `_epic.md`
  path — `wt --print-brief` resolves all three. Empty → ask, stop.
- **token 2** — `BASE` (required). Base branch to spawn off. `.` = cockpit's current branch.
- **rest** — `CONTEXT` (optional). Free-text notes for the lane.

## 2. Resolve the epic

`wt --print-brief <EPIC>` → `EPIC_MD`.
- **Non-zero exit / no path** → stop. Tell the user to `/scope` it into an epic first.
- **Resolved, but the path is not an `_epic.md`** → it's a single ticket, not an epic. Stop.
  Tell User: `/scope` it into an epic folder first (an `_epic.md` + `NN-<child>.md`
  children), or `wt <EPIC>` to work it as a single ticket.

`EPIC_DIR` = the directory holding `EPIC_MD`. `SLUG` = its basename.

## 3. Sync the cockpit to BASE

Skip if `BASE` == `.`.

```bash
git fetch --quiet origin
git rev-parse --verify "origin/<BASE>"   # missing → stop, report
git checkout "<BASE>"
git merge --ff-only "origin/<BASE>"
```

ff-merge fails (dirty tree / diverged) → stop, surface it. Never force.

## 4. Fold in context — only if `CONTEXT` non-empty

Append to `EPIC_MD` under `## Local notes` (create that section at end of file if missing):

```
### Epic note — <ISO-8601 date>
<CONTEXT>
```

It rides with the epic — every Ralph iteration reads `_epic.md`.

## 5. Confirm the story order

Read the `<!-- epic-stories:start -->` block in `EPIC_MD`. Print a terse numbered list —
`priority  id  title`, plus each story's `needs` edges. This block *is* the decomposition;
the user confirms it before the lane runs. Ralph will not re-plan it.

Ask: spawn the Ralph lane with this order, or stop so the user can edit the block in `EPIC_MD`
first? **Wait for "go".**

## 6. Spawn

```bash
wt --ralph <SLUG>
```

`wt --ralph <slug>` resolves the epic folder, branches off the now-current `BASE`, and the
lane: `ralph-bootstrap` → `~/.claude/scripts/epic-parse.sh <EPIC_MD> > scripts/ralph/prd.json`
→ stamps `branchName` + tunes `scripts/ralph/CLAUDE.md` test commands →
`./scripts/ralph/ralph.sh --tool claude`, one story per fresh-context iteration → `/ship` on
`<promise>COMPLETE</promise>`.

Branch type defaults to `feature/` — override with `wt --ralph --type <prefix> <SLUG>`.

## 7. Report, then stop

> Ralph lane spawned off `<BASE>`. Autonomous epic loop running in a new tmux window —
> <N> stories from `<EPIC_MD>`. This pane is done.

## Stop conditions

- Missing `EPIC` / `BASE`, or epic not found — ask or report, stop.
- Resolved to a single ticket, not an `_epic.md` — stop; tell the user to `/scope` it into an epic.
- ff-merge failure — surface, stop.
- User doesn't confirm the story order — stop, leave `EPIC_MD` for the user to edit.
- After spawn — done. Don't follow the lane.
