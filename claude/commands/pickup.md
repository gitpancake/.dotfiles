---
description: Pickup Linear ticket — materialize brief, sync base, fold context, spawn wt lane.
argument-hint: <TICKET> [BASE-BRANCH] [--fork] [extra context...]
---

# /pickup $ARGUMENTS

Wraps `wt` for the common pickup: materialize the ticket's brief from Linear (source of
truth), sync the cockpit to a base branch, fold in any extra context, spawn the lane. Do
**not** edit project source — this command only prepares and spawns.

## 1. Parse

`$ARGUMENTS` = `<TICKET> [BASE] [--fork] [context...]`:
- **token 1** — `TICKET` (required). A Linear id (`ENGH-123` — the normal case) or the slug
  of an already-materialized brief. Empty → ask, stop.
- **token 2** — `BASE` (optional, default `main`). Base branch to spawn off (or land onto —
  see §4). `.` = use the cockpit's current branch as-is. Token 2 is BASE only when it's `.`
  or names a real branch (`git rev-parse --verify --quiet "origin/<token2>" ||
  git show-ref --verify --quiet "refs/heads/<token2>"`); anything else means BASE was
  omitted → `BASE=main`, and token 2 onward is context. `/pickup ENGH-600` → `BASE=main`,
  synced to latest `origin/main` in §4.
- **`--fork`** (optional flag, anywhere after token 2) — force fork-off mode even when BASE
  is already checked out elsewhere. See §4.
- **rest** — `CONTEXT` (optional). Free-text notes for the lane.

## 2. Materialize the brief

`TICKET` is a Linear id (`^[A-Za-z]+-[0-9]+$`) — the normal case:
```bash
BRIEF=$(~/.dotfiles/scripts/linear-brief.sh "<TICKET>")
```
Fetches the issue's description over the Linear API and writes it as a local **cache** brief
(frontmatter `linear: <TICKET>`, `source: linear`) under `$TICKETS_DIR`, printing its path.
Idempotent (an existing materialization wins, never clobbered) — the file now lives on disk,
so `wt` resolves it by id on the spawn call (§5) and the lane reads it on every resume. The
brief is the Linear description verbatim; the lane plans slices from it as-is. Non-zero exit
(id not found in Linear) → stop, report. The cache file is never the source of truth — scope
changes go through `/rescope` (which refreshes it).

- **`TICKET` is a bare slug** → `wt --print-brief <TICKET>` (the resolver `wt` itself uses —
  don't re-implement). Path printed → use it, but check its `linear:` frontmatter; empty →
  the ticket never made it to Linear — tell the user to `/scope` it, stop. Non-zero exit →
  no such ticket anywhere; `/scope` it first, stop.
- **The Linear issue belongs to a project being driven as an epic** (has a project + sibling
  blocking relations) and the user seems to be working the epic → mention `/epic <project>
  <BASE>` confirms story order; proceed here only if they explicitly want this one child.

## 2.5. Move the ticket to its started state

Picking up = work starts now. Move the Linear issue (skip for a bare slug with no
`linear:` id):

```bash
~/.dotfiles/scripts/linear-ticket.py state --id "<TICKET>" --state "<STARTED>"
```

`STARTED` by team prefix: `ENGH-*` → `Execution` (that team has no "In Progress");
everything else → `In Progress`. Unknown name → the script dies listing the team's
states; rerun with its started-type name. Already started → script no-ops. Any failure
(network, key) → log one line and continue — never block the spawn on a state move.
(`In Review` comes later: `/ship` moves the ticket when the PR opens.)

## 3. Fold in context — only if `CONTEXT` non-empty

Append to `BRIEF` under `## Local notes` (create that section at end of file if missing):

```
### Pickup note — <ISO-8601 date>
<CONTEXT>
```

It rides with the brief — the lane reads it, and it survives `/handoff`.

## 4. Resolve mode — fork-off vs onto

Two modes:

- **fork-off** (default for `main` / `master` / `develop` / `staging`, or when `--fork`
  passed): cockpit syncs to BASE, `wt` branches `<type>/<TICKET>` off BASE. Commits land on
  the new branch.
- **onto** (default for feature-branch BASE already checked out in another worktree):
  cockpit is untouched, `wt --branch <BASE> <TICKET>` reuses that worktree. Commits land on
  BASE itself — the right shape for "more commits on an open PR."

### Detect

```bash
existing_wt=$(git worktree list --porcelain \
  | awk -v b="refs/heads/<BASE>" '/^worktree /{w=substr($0,10)} /^branch /{if($2==b){print w; exit}}')
```

- `existing_wt` non-empty AND `--fork` not set AND BASE not in `main|master|develop|staging`
  → **onto mode**. Announce pivot:
  > BASE `<BASE>` checked out at `<existing_wt>` — landing commits onto BASE itself.
  > Override w/ `--fork` to branch off instead.
- Otherwise → **fork-off mode**. Continue below.

### Fork-off: sync the cockpit to BASE

Skip if `BASE` == `.`.

```bash
git fetch --quiet origin
git rev-parse --verify "origin/<BASE>"   # missing → stop, report
git checkout "<BASE>"
git merge --ff-only "origin/<BASE>"
```

ff-merge fails because BASE has local-only commits (diverged, clean tree) →
`git rebase "origin/<BASE>"` and continue; report the rebased commits in the final
message. Rebase hits conflicts → `git rebase --abort`, stop, surface. Dirty tree →
stop, surface. Never force-push, never discard local commits.

### Onto: skip cockpit sync

Cockpit ff-merge would fail anyway (git refuses to check out a branch held by another
worktree). Skip §4 sync entirely. Existing worktree is the source of truth; `wt` will
reuse it as-is.

## 5. Spawn the lane

Run via the Bash tool — opens a new tmux window w/ claude in autonomous mode.

- **fork-off**:
  ```bash
  wt --base <BASE> <TICKET>
  ```
  Branches `<type>/<TICKET>` off `BASE`, creates worktree + per-lane port. `--base` is
  required even after the cockpit sync — without it `wt` defaults to origin's default
  branch, not the cockpit HEAD. For `BASE` == `.` use `--base HEAD`. Branch type defaults
  to `feature/` — for `fix/` or `refactor/`, run `wt --type <prefix> --base <BASE> <TICKET>`
  directly.

- **onto**:
  ```bash
  wt --branch <BASE> <TICKET>
  ```
  Reuses existing worktree of `<BASE>` (line 296 of `wt` auto-detects). Lane reads `BRIEF`,
  commits land on `<BASE>`.

Report, then stop:

> Lane spawned (`<mode>`) on `<BASE>`. Autonomous dev loop running in new tmux window. This pane is done.

## Stop conditions

- Missing `TICKET` — ask, stop. (Missing `BASE` is not a stop — defaults to `main`.)
- Ticket not found in Linear (and no materialized brief for a bare slug) — report, stop and
  point at `/scope`. A Linear id that *does* resolve is materialized in §2, not a stop.
- Cockpit sync unrecoverable (fork-off mode): dirty tree, or rebase conflict after
  abort — surface, stop. (Clean divergence auto-rebases, not a stop.)
- After spawn — done. Don't follow the lane.
