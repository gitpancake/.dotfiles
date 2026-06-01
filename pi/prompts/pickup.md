---
description: Pick up a local ticket brief in Pi or spawn the existing wt lane workflow.
argument-hint: <TICKET> <BASE-BRANCH|.> [--spawn-wt] [--fork] [extra context...]
---

# /pickup $ARGUMENTS

Resolve a local brief, fold in optional context, sync/check the base, then either continue in this Pi session or spawn `wt` when explicitly requested.

Default is Pi-native: continue inline in the current session. Use `--spawn-wt` to hand off to the external `wt` lane workflow.

## Parse

`$ARGUMENTS` = `<TICKET> <BASE> [--spawn-wt] [--fork] [context...]`

- `TICKET` required: slug, local filename handle, or external breadcrumb resolvable by `wt`.
- `BASE` required: branch to base from. `.` means current branch.
- `--spawn-wt`: run `wt` after preparation and stop.
- `--fork`: when spawning `wt`, force branch-off mode instead of landing onto an existing feature branch worktree.
- Remaining text: append as pickup context to the brief.

Missing `TICKET` or `BASE`: ask and stop.

## Locate brief

Prefer `wt --print-brief <TICKET>` if available. If not, search `${TICKETS_DIR:-$HOME/.claude/tickets}` for `<TICKET>.md` or matching filename slug.

- Not found: tell the user to `/scope` it first and stop.
- `_epic.md`: stop and tell the user to use the epic workflow; `/pickup` is for one ticket.

Read the brief before acting.

## Fold context

If extra context exists, append to the brief under `## Local notes`:

```md
### Pickup note — <UTC ISO-8601>
<context>
```

## Base check

Run:

- `git status --short --branch`
- `git branch --show-current`

If `BASE != .` and the tree is clean, fetch and fast-forward/check out the base:

```bash
git fetch --quiet origin
git rev-parse --verify origin/<BASE>
git checkout <BASE>
git merge --ff-only origin/<BASE>
```

If dirty, diverged, missing, or checkout would collide with another worktree, surface the exact state and ask before changing branches.

## Pi-native default

Do not spawn anything. Orient in two lines:

`Picked up <brief> on <branch/base>.`
`Next: <first implementation or investigation step>.`

Then proceed using Pi tools, respecting the brief and project instructions.

## Optional wt spawn

Only if `--spawn-wt` is present:

- If `BASE` is a feature branch already checked out elsewhere and `--fork` is absent, run `wt --branch <BASE> <TICKET>`.
- Otherwise sync to `BASE` and run `wt <TICKET>`.

After spawning, report the mode and stop. Do not follow the lane.
