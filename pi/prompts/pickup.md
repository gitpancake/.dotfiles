---
description: Pick up a local ticket brief and continue Pi-native in this session.
argument-hint: <TICKET> <BASE-BRANCH|.> [extra context...]
---

# /pickup $ARGUMENTS

Resolve a local brief, fold in optional context, sync/check the base, then continue in this Pi session.

Stay Pi-native. Use `/tree`, `/fork`, or `/clone` for alternate approaches instead of starting external workers.

## Parse

`$ARGUMENTS` = `<TICKET> <BASE> [context...]`

- `TICKET` required: slug, local filename handle, or external breadcrumb resolvable in the ticket directory.
- `BASE` required: branch to base from. `.` means current branch.
- Remaining text: append as pickup context to the brief.

Missing `TICKET` or `BASE`: ask and stop.

## Locate brief

Search `${PI_TICKETS_DIR:-$HOME/.pi/tickets}` for `<TICKET>.md` or matching filename slug.

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

## Continue Pi-native

Do not start external workers. Orient in two lines:

`Picked up <brief> on <branch/base>.`
`Next: <first implementation or investigation step>.`

Then proceed using Pi tools, respecting the brief and project instructions.

If the brief is broad or risky, branch the session with `/tree` before implementation. If the session becomes long, write `/handoff` before changing strategy or shipping.
