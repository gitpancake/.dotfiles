---
description: Rebase feature onto base. Auto-resolve conflicts, escalate ambiguous, push on clean replay. Force-push on confirm.
argument-hint: <base> <feature> — e.g. `main feature/ae-1700-foo`. If only one arg, assumes current branch is the feature.
---

# /rebase $ARGUMENTS

Fetch → rebase → resolve trivial conflicts → escalate ambiguous ones → push. Never force-pushes without explicit confirmation.

## 0. Parse arguments

Tokens from `$ARGUMENTS`:
- **two tokens** → `BASE=<arg1>` `FEATURE=<arg2>`
- **one token** → `BASE=<arg1>` `FEATURE=$(git branch --show-current)`
- **zero tokens** → refuse. Print usage. Stop.

Validate:
- `FEATURE` ≠ `main`/`master` → refuse.
- `git rev-parse --verify "$FEATURE" 2>/dev/null` — branch presence check.
  - Local exists → `MODE=local`. Continue §1.
  - Missing locally → `git fetch origin "$FEATURE" --prune` then `git rev-parse --verify "origin/$FEATURE"`.
    - Exists on origin → `MODE=worktree`. Continue §1.
    - Missing on origin too → stop. Print: `Branch $FEATURE not found locally or on origin.`
- `BASE` may be local or remote; we always rebase onto `origin/$BASE` after fetch.

## 1. Pre-flight (parallel)

`MODE=local`:
- `git status --porcelain` — must be clean. Dirty → stop, surface files, ask user to commit/stash.
- `git branch --show-current` → `STARTING_BRANCH`.
- `git rev-parse "$FEATURE"@{u} 2>/dev/null` → `FEATURE_UPSTREAM`.
- Ongoing rebase (`.git/rebase-merge` or `.git/rebase-apply`) → stop, tell user to `--abort` or `--continue`.

`MODE=worktree`:
- Skip clean-tree check (worktree is isolated).
- `STARTING_BRANCH` unset (we never leave the cockpit).
- `FEATURE_UPSTREAM=origin/$FEATURE` (remote-only branch).
- `WT=$(mktemp -d -t rebase-${FEATURE//\//-}-XXXX)` → throwaway worktree path. Remember it.

## 2. Fetch base

```
git fetch origin "$BASE" --prune
```

Fail → stop, surface error.

## 3. Position on feature

`MODE=local`:
```
git checkout "$FEATURE"
```

`MODE=worktree`:
```
git worktree add "$WT" -B "$FEATURE" "origin/$FEATURE"
cd "$WT"
```
All subsequent git calls run inside `$WT` until cleanup.

## 4. Rebase + intelligent conflict loop

```
git rebase "origin/$BASE"
```

Loop until rebase finishes or escalates:

- **Clean replay / already up-to-date** → continue §5.
- **Conflict** → inspect:
  - `git status --porcelain`
  - `git diff --name-only --diff-filter=U` → conflicted files
  - For each conflicted file: read full file, examine `<<<<<<<` / `=======` / `>>>>>>>` blocks, `git log --oneline -5 HEAD` and `git log --oneline -5 REBASE_HEAD` for context.

  Auto-resolve **only** when resolution is unambiguous:
  - Import/require lists, package.json deps, lockfile-style additive blocks → union of both sides, dedupe.
  - Whitespace/formatting-only conflicts → take incoming (`origin/$BASE`) side.
  - One side deletes a line the other side only reformats → keep the reformat.
  - Adjacent but non-overlapping edits the merge driver mis-flagged → take both.
  - Generated files (lockfiles, snapshots) → regenerate if a known command exists; otherwise escalate.

  Escalate (stop, do **not** guess) when:
  - Same lines edited semantically on both sides.
  - Business logic, control flow, or type signatures conflict.
  - File deleted on one side, modified on the other.
  - Any uncertainty about intent.

  Auto-resolve path:
  1. Edit file to resolved state.
  2. `git add <file>`.
  3. After all auto-resolvable files staged: `git rebase --continue`.
  4. Loop back to top of §4.

  Escalation path → STOP. Print:
  ```
  Rebase paused — ambiguous conflicts need user:
    <file>:<line-range> — <one-line reason>
    ...
  Worktree: $WT   (MODE=worktree only)
  Resolve, `git add <files>`, then `git rebase --continue`.
  Or `git rebase --abort` to bail.
  ```
  Do **not** delete worktree. Do **not** push.

## 5. Push

If `FEATURE_UPSTREAM` unset (only possible in `MODE=local`):
```
git push -u origin "$FEATURE"
```

If rebase rewrote history (local SHAs differ from `FEATURE_UPSTREAM`):
- **Confirm with user before force-pushing.** Show:
  ```
  Force-push required (rebase rewrote $FEATURE history).
  Upstream: $FEATURE_UPSTREAM
  Local:    $FEATURE @ <new-sha>
  Run `git push --force-with-lease`? [y/N]
  ```
  `y` → `git push --force-with-lease origin "$FEATURE"`.
  Otherwise stop. Print the command. Skip cleanup so user can push from `$WT` if needed.

Fast-forward only → plain `git push`.

Rejected push (non-force case) → surface error, stop. Do not auto-retry.

## 6. Cleanup

`MODE=worktree` AND push succeeded:
```
cd -
git worktree remove "$WT"
git branch -D "$FEATURE"   # local ref created by `worktree add -B` — branch lives on origin
```
Push skipped or escalated → keep worktree, print path.

`MODE=local`:
- If `STARTING_BRANCH` ≠ `$FEATURE` and was a real branch → `git checkout "$STARTING_BRANCH"`. Skip on detached HEAD.

## 7. Report — terse

```
Rebased $FEATURE onto origin/$BASE   (mode: <local|worktree>)
Commits replayed: <N>
Auto-resolved: <file count or "none">
Push: <pushed | force-pushed | skipped — manual>
Worktree: <removed | $WT preserved>
```

## 8. Stop

Do not amend pre-existing commits. Do not open a PR. Do not trigger review. Ambiguous conflicts → user resolves.
