---
description: Rebase a feature branch onto a base branch. Fetches base, rebases, reports conflicts, pushes on clean replay. Force-push only on confirmation.
argument-hint: <base> <feature> — e.g. `main feature/ae-1700-foo`. If only one arg, assumes current branch is the feature.
---

# /rebase $ARGUMENTS

Mechanical fetch → rebase → conflict report → push. Never resolves conflicts silently.
Never force-pushes without explicit confirmation.

## 0. Parse arguments

Tokens from `$ARGUMENTS`:
- **two tokens** → `BASE=<arg1>` `FEATURE=<arg2>`
- **one token** → `BASE=<arg1>` `FEATURE=$(git branch --show-current)`
- **zero tokens** → refuse. Print usage. Stop.

Validate:
- `git rev-parse --verify "$FEATURE"` — local branch must exist. Missing → check `origin/$FEATURE`; if remote-only, offer `git checkout -b $FEATURE origin/$FEATURE`. Otherwise stop.
- `FEATURE` ≠ `main`/`master` → refuse.
- `BASE` may be local or remote; we always rebase onto `origin/$BASE` after fetch.

## 1. Pre-flight (parallel)

Run in parallel:
- `git status --porcelain` — must be clean. Dirty → stop, surface files, ask user to commit/stash.
- `git branch --show-current` — remember `STARTING_BRANCH`.
- `git rev-parse "$FEATURE"@{u} 2>/dev/null` — capture upstream if any (`FEATURE_UPSTREAM`).
- `git log --oneline "origin/$BASE..$FEATURE" 2>/dev/null | wc -l` — commit count ahead pre-rebase.

Stop conditions:
- Dirty tree → stop.
- Ongoing rebase (`.git/rebase-merge` or `.git/rebase-apply` exists) → stop, tell user to `--abort` or `--continue` first.

## 2. Fetch base

```
git fetch origin "$BASE" --prune
```

Fail → stop, surface error.

## 3. Checkout feature

```
git checkout "$FEATURE"
```

Already on it → no-op. Different branch → switch. Failure (uncommitted local changes blocking) → stop.

## 4. Rebase

```
git rebase "origin/$BASE"
```

Outcomes:
- **Clean replay** → continue §5.
- **Conflicts** → STOP. Do not attempt auto-resolution. Run `git status --porcelain` and `git diff --name-only --diff-filter=U`. Report:
  ```
  Rebase paused on conflicts:
    <file1>
    <file2>
  Resolve, `git add <files>`, then `git rebase --continue`. Or `git rebase --abort` to bail.
  ```
  Stop. Do not push. Do not call `--continue` yourself.
- **Already up-to-date** (no commits to replay) → note it, skip to §5 anyway in case push state diverges.

## 5. Push

If `FEATURE_UPSTREAM` was unset (no remote tracking):
```
git push -u origin "$FEATURE"
```

If `FEATURE_UPSTREAM` exists and rebase rewrote history (commit count ahead of base unchanged, but local SHAs differ from upstream):
- **Confirm with user before force-pushing.** Show:
  ```
  Force-push required (rebase rewrote $FEATURE history).
  Upstream: $FEATURE_UPSTREAM
  Local:    $FEATURE @ <new-sha>
  Run `git push --force-with-lease`? [y/N]
  ```
  On `y` → `git push --force-with-lease origin "$FEATURE"`.
  Otherwise stop. Print the command for manual run.

If no rewrite (fast-forward only): plain `git push`.

Rejected push (non-force case) → surface error, stop. Do not auto-retry.

## 6. Restore starting branch (optional)

If `STARTING_BRANCH` ≠ `$FEATURE` and was a real branch → `git checkout "$STARTING_BRANCH"`. Skip on detached HEAD.

## 7. Report — terse

```
Rebased $FEATURE onto origin/$BASE
Commits replayed: <N>
Push: <pushed | force-pushed | skipped — manual>
```

## 8. Stop

Do not amend commits. Do not open a PR. Do not trigger review. Conflicts → user resolves.
