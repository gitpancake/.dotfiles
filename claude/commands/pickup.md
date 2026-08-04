---
description: Pickup local ticket brief — sync base, fold context, spawn wt lane.
argument-hint: <TICKET> <BASE-BRANCH> [--fork] [extra context...]
---

# /pickup $ARGUMENTS

Wraps `wt` for the common pickup: resolve a brief from `<TICKET>`, sync the cockpit to a base
branch, fold in any extra context, spawn the lane. Do **not** edit project source — this
command only prepares and spawns.

## 1. Parse

`$ARGUMENTS` = `<TICKET> <BASE> [--fork] [context...]`:
- **token 1** — `TICKET` (required). A ticket slug, a Linear id, or an epic folder name —
  `wt` resolves all three. Empty → ask, stop.
- **token 2** — `BASE` (required). Base branch to spawn off (or land onto — see §4).
  `.` = use the cockpit's current branch as-is.
- **`--fork`** (optional flag, anywhere after token 2) — force fork-off mode even when BASE
  is already checked out elsewhere. See §4.
- **rest** — `CONTEXT` (optional). Free-text notes for the lane.

## 2. Locate the brief

`wt --print-brief <TICKET>` → `BRIEF`. This is the one resolver `wt` itself uses (Linear id →
slug → epic folder name) — do **not** re-implement the lookup here.
- **Path printed** → use it.
- **Non-zero exit AND `TICKET` is a Linear id** (`^[A-Za-z]+-[0-9]+$`) → the brief isn't local
  yet, but Linear is the source of truth for it. Pull it down instead of stopping:
  ```bash
  BRIEF=$(~/.dotfiles/scripts/linear-brief.sh "<TICKET>")
  ```
  Fetches the ticket's description over the Linear API and writes it as a real local brief
  (frontmatter `linear: <TICKET>`, `source: linear`) under `$TICKETS_DIR`, printing its path.
  It's idempotent (an existing/hand-`/scope`d brief wins, never clobbered) and self-healing —
  the file now lives on disk, so `wt` resolves it by id on the spawn call (§5) and the lane
  reads it on every resume. **No `/scope` required.** The brief is the Linear description
  verbatim (not grilled); the lane plans slices from it as-is. Non-zero exit (id not found in
  Linear) → stop, report.
- **Non-zero exit AND `TICKET` is a bare slug** (no Linear id to read from) → stop. Tell the
  user to `/scope` it first.
- **`basename "$BRIEF"` == `_epic.md`** → it's an epic, wrong command. Stop:
  > Resolved to epic `<TICKET>`. Use `/epic <TICKET> <BASE>` to confirm story order +
  > spawn the next child lane. `/pickup` is for single tickets only.

  Story-order confirmation in `/epic` is the contract that keeps epic execution
  deterministic — don't bypass it by auto-routing.

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

ff-merge fails (dirty tree / diverged) → stop, surface it. Never force.

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

- Missing `TICKET` / `BASE` — ask, stop.
- Brief not found locally AND not on Linear (bare slug, or Linear id that doesn't exist) —
  report, stop. A Linear id that *does* resolve is materialized in §2, not a stop.
- Resolved to an epic (`_epic.md`) — stop, redirect to `/epic`.
- ff-merge failure (fork-off mode) — surface, stop.
- After spawn — done. Don't follow the lane.
