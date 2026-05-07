# Worktree Protocol

Assume another agent may be active on any branch. Default = isolate work in a git worktree.

## Before starting non-trivial work

1. Survey: `git worktree list --porcelain`. Note existing worktrees and their branches.
2. Spawn: `git worktree add ../<repo>-wt-<task> -b agent/<task>`
   - For delegated subagent work: `Agent(..., isolation: "worktree")` (auto-cleans if no changes made).
3. `cd` into the new worktree. All edits, commits, dev servers run there.
4. Never operate on the shared checkout while another session may be active.

## Skip worktree only for

- Read-only inspection (grep, read, status checks).
- Single trivial edit (one line, one file, no logic).
- Explicit user override.

## Gotchas

- `node_modules` is **not** shared between worktrees. Install per worktree if needed.
- Dev servers on same port collide across worktrees. Assign a unique port per worktree.
- `.git` is shared — commits in one worktree are immediately visible to all.
- Branch can only be checked out in one worktree at a time.

## Cleanup — manual, user-confirmed only

Trigger when user confirms PR merged. Never auto-cleanup. Never act on `gh pr view` poll alone.

```
git worktree remove ../<repo>-wt-<task>
git branch -d agent/<task>
git worktree prune
```

If worktree dirty: surface state to user, ask before `--force`.
If branch unmerged: ask before `-D`.

## Naming

- Worktree path: `../<repo>-wt-<task>` (sibling to repo).
- Branch: `agent/<short-task>`.
- Squash-merge winner if multiple parallel attempts; discard losing branches.
