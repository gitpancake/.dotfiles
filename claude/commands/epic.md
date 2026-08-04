---
description: Pickup epic (Linear project) — confirm story order, spawn next child as single lane.
argument-hint: <EPIC> <BASE-BRANCH> [extra context...]
---

# /epic $ARGUMENTS

Drives an epic as a sequence of single lanes.

An **epic** is a Linear **project**: children = issues carrying per-story detail, blocking
relations = the authoritative dependency DAG (global CLAUDE.md §Ticket Lifecycle). `/epic`
reads the project from Linear, confirms the next story with the user, then spawns it as a
normal `wt` single lane. Re-run `/epic` after each child's PR merges to spawn the next — the
command is resumable; Linear issue state is the progress marker.

Syncs the cockpit to a base branch, folds in any extra context, spawns one lane. Do **not**
edit project source — this command only prepares and spawns.

## 1. Parse

`$ARGUMENTS` = `<EPIC> <BASE> [context...]`:
- **token 1** — `EPIC` (required). A Linear project name fragment, project URL, or any child
  issue id (its `project` field resolves the epic). Empty → ask, stop.
- **token 2** — `BASE` (required). Base branch to spawn off. `.` = cockpit's current branch.
- **rest** — `CONTEXT` (optional). Free-text notes for the story about to spawn.

## 2. Resolve the epic

Via the `linear` skill: `projects(filter: {name: {containsIgnoreCase: ...}})` (or
`issue(id:){ project }` for a child id) → project id. Then fetch children + DAG in one query:

```graphql
query($id: String!) { project(id: $id) {
  name url
  issues(first: 50) { nodes {
    identifier title sortOrder
    state { name type }
    relations { nodes { type relatedIssue { identifier } } }
    inverseRelations { nodes { type issue { identifier } } }
} } } }
```

- **No project matches / ambiguous** → list candidates or stop; tell the user to `/scope`
  the epic first if it doesn't exist.
- **Resolved to a lone issue with no project** → it's a single ticket, not an epic. Stop:
  use `/pickup <id> <BASE>` instead.

## 3. Sync the cockpit to BASE

Skip if `BASE` == `.`.

```bash
git fetch --quiet origin
git rev-parse --verify "origin/<BASE>"   # missing → stop, report
git checkout "<BASE>"
git merge --ff-only "origin/<BASE>"
```

ff-merge fails (dirty tree / diverged) → stop, surface it. Never force.

## 4. Pick the next child + confirm

Classify every child by Linear `state.type`:

- `completed` / `canceled` → done, skip.
- `started` → in flight. Stop and report — don't double-spawn a story.
- `backlog` / `unstarted` → candidate.

**NEXT** = the candidate whose blockers (issues that *block* it, via relations) are all
`completed`/`canceled`, lowest `sortOrder` (ties: lowest identifier). No candidate and
nothing in flight → epic done; say so, stop.

Print a terse numbered list — `identifier  title  state`, marking NEXT — and ask: spawn
NEXT, or stop so the user can re-order / `/rescope` children first? **Wait for "go".** The
project's DAG *is* the decomposition; never re-plan it here.

## 5. Fold in context — only if `CONTEXT` non-empty

After "go", `CONTEXT` rides with the child: post it as a comment on NEXT's Linear issue
(`commentCreate`), so it survives materialization refreshes and is visible to the team.

## 6. Spawn

```bash
BRIEF=$(~/.dotfiles/scripts/linear-brief.sh "<NEXT-ID>")
wt <NEXT-ID>
```

`linear-brief.sh` materializes the child's description as the lane's local cache brief; `wt`
resolves it by the `linear:` frontmatter. Normal single lane off the now-current `BASE`: the
brief drives it end-to-end through `/ship`. Branch type defaults to `feature/` — override
with `wt --type <prefix> <NEXT-ID>`.

## 7. Report, then stop

> Lane spawned for `<NEXT-ID>` (<k> of <N> stories complete) off `<BASE>`. Re-run
> `/epic <EPIC> <BASE>` after its PR merges to spawn the next story. This pane is done.

## Stop conditions

- Missing `EPIC` / `BASE`, or project not found — ask or report, stop.
- Resolved to a single project-less issue — stop; redirect to `/pickup`.
- ff-merge failure — surface, stop.
- A child is already `started` — report it, stop. One story in flight at a time.
- User doesn't confirm NEXT — stop; they'll re-order or `/rescope` in Linear first.
- After spawn — done. Don't follow the lane.
