---
description: Pickup epic — confirm story order, spawn next child as single lane.
argument-hint: <EPIC> <BASE-BRANCH> [extra context...]
---

# /epic $ARGUMENTS

Drives an epic as a sequence of single lanes. (The Ralph loop was retired 2026-06-09 —
`wt --ralph`, `epic-parse.sh`, and `scripts/ralph/` no longer exist.)

An **epic** is a folder with an `_epic.md` at its root (contract: `$TICKETS_DIR/README.md`),
holding the `<!-- epic-stories:start -->` block — the authoritative ordered story list +
dependency DAG — plus one `NN-<child>.md` brief per story. `/epic` confirms that order with
the user, then spawns the **next incomplete child** as a normal `wt` single lane. Re-run
`/epic` after each child's PR merges to spawn the next — the command is resumable; child
`status:` frontmatter (kept current by ticket-status-sync) is the progress marker.

Syncs the cockpit to a base branch, folds in any extra context, spawns one lane. Do **not**
edit project source — this command only prepares and spawns.

## 1. Parse

`$ARGUMENTS` = `<EPIC> <BASE> [context...]`:
- **token 1** — `EPIC` (required). An epic folder slug, a Linear epic id, or an `_epic.md`
  path — `wt --print-brief` resolves all three. Empty → ask, stop.
- **token 2** — `BASE` (required). Base branch to spawn off. `.` = cockpit's current branch.
- **rest** — `CONTEXT` (optional). Free-text notes for the epic.

## 2. Resolve the epic

`wt --print-brief <EPIC>` → `EPIC_MD`.
- **Non-zero exit / no path** → stop. Tell the user to `/scope` it into an epic first.
- **Resolved, but the path is not an `_epic.md`** → it's a single ticket, not an epic. Stop.
  Tell user: `/scope` it into an epic folder first (an `_epic.md` + `NN-<child>.md`
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

It rides with the epic — child briefs reference `_epic.md` for shared context.

## 5. Pick the next child + confirm

Read the `<!-- epic-stories:start -->` block in `EPIC_MD` and the `status:` frontmatter of
every `NN-<child>.md` in `EPIC_DIR`:

- `done` / `cancelled` → complete, skip.
- `review` / `active` → in flight. Stop and report — don't double-spawn a story.
- Anything else (`open`, `draft`, missing) → candidate.

**NEXT** = the lowest-`NN` candidate whose `needs` edges (from the stories block) all point
at complete children. No candidate and nothing in flight → epic done; say so, stop.

Print a terse numbered list — `NN  child  status`, marking NEXT — and ask: spawn NEXT, or
stop so the user can edit the stories block / briefs first? **Wait for "go".** The stories
block *is* the decomposition; never re-plan it here.

## 6. Spawn

```bash
wt <NN-CHILD-SLUG>
```

Normal single lane off the now-current `BASE`: the child brief drives it end-to-end through
`/ship`. Branch type defaults to `feature/` — override with `wt --type <prefix> <slug>`.

## 7. Report, then stop

> Lane spawned for `<NN-child>` (<k> of <N> stories complete) off `<BASE>`. Re-run
> `/epic <EPIC> <BASE>` after its PR merges to spawn the next story. This pane is done.

## Stop conditions

- Missing `EPIC` / `BASE`, or epic not found — ask or report, stop.
- Resolved to a single ticket, not an `_epic.md` — stop; tell the user to `/scope` it into an epic.
- ff-merge failure — surface, stop.
- A child is already `active`/`review` — report it, stop. One story in flight at a time.
- User doesn't confirm NEXT — stop, leave `EPIC_MD` for the user to edit.
- After spawn — done. Don't follow the lane.
