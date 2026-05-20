---
description: Rebase every open PR of yours onto its base. Per-PR worktree, auto-resolve trivial conflicts, escalate ambiguous, force-push clean replays on confirm.
argument-hint: "[base] [--author <login>] — base defaults to each PR's own baseRefName; --author defaults to @me"
---

# /rebase-all $ARGUMENTS

The fan-out `/rebase` doesn't cover: "merge latest main into all my open PRs." Enumerate your open PRs, rebase each onto its base in a throwaway worktree, auto-resolve trivial conflicts, **escalate ambiguous ones per-PR** (one messy PR never blocks the rest), force-push clean replays after one batch confirm. Never touches the cockpit checkout.

This reuses `/rebase`'s conflict doctrine verbatim — read §4 of `/rebase` for the auto-resolve-vs-escalate rules. This command is the loop around it, not a re-spec.

## 0. Parse arguments

Tokens from `$ARGUMENTS`:
- A bare token (not `--…`) → `BASE_OVERRIDE=<token>` — rebase **every** PR onto `origin/<token>` regardless of its own base. Use for "merge latest main into all my PRs."
- `--author <login>` → `AUTHOR=<login>`. Default `AUTHOR=@me`.
- No bare token → `BASE_OVERRIDE` unset; each PR rebases onto its **own** `baseRefName` (correct for stacked PRs).

## 1. Enumerate target PRs

```
gh pr list --author "$AUTHOR" --state open --json number,headRefName,baseRefName,title,isDraft,mergeable
```

- Empty → "No open PRs for $AUTHOR." Stop.
- Build the work list: one row per PR = `{ num, head, base: BASE_OVERRIDE or baseRefName, title }`.
- Skip + note any PR whose `head` equals its `base` (nothing to rebase) and any cross-repo PR if the current repo can't resolve `head`.

Print the plan before doing anything:

```
Rebasing N PRs (author: $AUTHOR, base: <override or per-PR>):
  #123  feature/foo        → origin/main
  #124  feature/bar        → origin/feature/foo   (stacked)
  ...
```

## 2. One batch confirm

Rebase rewrites history → every clean PR needs a force-push. Confirm once for the batch:

```
This will rebase + force-push-with-lease N branches. Ambiguous conflicts pause that PR (no push). Proceed? [y/N]
```

`n` / anything but `y` → stop, change nothing.

## 3. Per-PR loop (sequential)

For each PR row, run the `/rebase` worktree-mode flow. Sequential, not parallel — parallel worktrees off the same repo race on `git fetch` and the object store.

```
git fetch origin "$base" "$head" --prune
WT=$(mktemp -d -t rebaseall-${head//\//-}-XXXX)
git worktree add "$WT" -B "$head" "origin/$head"
git -C "$WT" rebase "origin/$base"
```

Then resolve per `/rebase` §4:
- **Clean replay / already up-to-date** → if history changed, `git -C "$WT" push --force-with-lease origin "$head"`; if already up-to-date, no push. Record result. Remove worktree + local branch ref (`git worktree remove "$WT"; git branch -D "$head"`).
- **Trivial conflicts** (import/dep unions, whitespace, lockfile regen, non-overlapping edits the driver mis-flagged) → auto-resolve, `git add`, `git rebase --continue`, loop. Then push as above.
- **Ambiguous conflicts** (same lines edited semantically, logic/types/control-flow, delete-vs-modify, any doubt) → **do not guess, do not push**. `git -C "$WT" rebase --abort` to leave the branch unmoved on origin, record `skipped — conflict`, **keep the worktree**, capture the conflicted `file:line` list. Move to the next PR.

Failures (`fetch`/`worktree add`/`push` rejected) → record `failed — <reason>`, keep worktree, continue to next PR. Never auto-retry, never `--force` without `--with-lease`.

## 4. Report — table

```
Rebase-all (author: $AUTHOR) onto <override or per-PR base>

  PR     Branch                Result
  #123   feature/foo           rebased + force-pushed (3 replayed, 1 auto-resolved)
  #124   feature/bar           up-to-date
  #125   fix/baz               skipped — conflict (src/x.ts:40-58)  WT: /tmp/rebaseall-fix-baz-AB12
  #126   feature/qux           failed — push rejected (stale lease)  WT: /tmp/...

Pushed: 1   Up-to-date: 1   Skipped: 1   Failed: 1
```

For every skipped/failed PR, print the preserved worktree path + the resolve hint (`cd <WT>`, resolve, `git add`, `git rebase --continue`, `git push --force-with-lease`). Removed worktrees only for clean PRs.

## 5. Stop

Do not open PRs, trigger reviews, or amend pre-existing commits. Ambiguous conflicts are the user's to resolve in the preserved worktree. This command rebases what's safe and reports the rest — it does not push through uncertainty.
