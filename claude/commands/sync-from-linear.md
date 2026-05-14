---
description: Batch-pull user's Linear tickets into local markdown under ~/.claude/tickets/<PARENT>/<TICKET>.md so agents and wt lanes work from the file system, not live MCP calls.
argument-hint: "[optional: --state backlog,todo,in-progress,in-review to filter]"
---

# /sync-from-linear $ARGUMENTS

The **read** half of the Linear boundary. Run this occasionally — morning, or when taking
on new work — **not** per ticket pickup. It replaces `/ticket-pickup`'s live per-ticket MCP
read with one batch sync. After this runs, `wt` lanes and Ralph read from
`~/.claude/tickets/`; no live Linear call happens inside the work loop.

## 1. Argument parsing

`$ARGUMENTS` may contain `--state <comma-list>`. Default states:
`backlog, todo, in progress, in review`. Anything else → ignore.

## 2. Fetch the index (one call)

`mcp__linear-server__list_issues` filtered to `assignee = user` (the current Linear user)
and the states from §1. Pull: `id`, `title`, `state`, `parent`, `project`, `labels`, `url`,
`updatedAt`. This is the index — cheap, one round-trip.

## 3. Fetch bodies (the batch)

For each issue in the index, `mcp__linear-server__get_issue <ID>` for the description +
acceptance criteria. This is the batch read — N calls, once, occasionally. That's the
deliberate trade: pay it here, never in the work loop.

## 4. Resolve `<PARENT>`

Epic dirs are **human-readable slugs**, not raw IDs — the mapping lives in
`~/.claude/tickets/.epics.json` (`{ "TEAM-1589": "some-epic-slug", ... }`), keyed by
Linear epic ID (upper-case, as in frontmatter).

Per ticket, in order:
1. **This ticket is itself an epic** (its ID is a key in `.epics.json`, i.e. other synced
   tickets parent to it) → use its own mapped slug, so the epic file sits beside its
   sub-issues at `<slug>/<EPIC-ID>.md`.
2. **This ticket has a Linear `parent`** → look the parent ID up in `.epics.json`.
   - Hit → use the mapped slug.
   - Miss → generate a short human-readable kebab slug from the parent epic's title
     (≤4 words, e.g. `some-epic-slug`), append `"<PARENT-ID>": "<slug>"` to
     `.epics.json`, then use it. **Never fall back to the raw `team-1600`-style ID.**
3. Else the Linear project slug (lowercased, non-alnum → `-`).
4. Else `_loose`.

`.epics.json` is the durable name map — read it at the start of the sync, write any new
entries back at the end.

## 5. Write `~/.claude/tickets/<PARENT>/<TICKET>.md`

```
---
id: TEAM-1692
parent: TEAM-1600
title: <ticket title>
status: In Progress
project: <project-slug>
labels: [<label>, feature]
url: https://linear.app/...
synced: <ISO-8601 now>
---

## Context
<ticket description, verbatim>

## Acceptance criteria
- <copied from ticket; none in ticket → write "none specified in Linear">

## Local notes
<!-- preserved across syncs — agent / wt / ralph scratch lives here -->
```

`mkdir -p` the parent dir first.

## 6. Idempotency

- **Existing file**: regenerate everything from the frontmatter through the end of
  `## Acceptance criteria`. **Preserve `## Local notes` and everything below it verbatim.**
- **Parent changed** (the §4-resolved `<PARENT>` slug differs from the dir the file
  currently sits in): write the file at the new path, then replace the old file with a
  one-line tombstone: `moved → ~/.claude/tickets/<NEW-PARENT>/<TICKET>.md`.
- **Ticket no longer in the index** (closed/cancelled/reassigned since last sync): leave the
  local file untouched — don't delete. List it under "stale" in the report so user decides.

## 7. Report — terse

Group by parent:

```
synced 14 tickets → ~/.claude/tickets/

some-epic-slug/  (epic TEAM-1589)
  TEAM-1692  In Progress  <ticket title>
  TEAM-1693  Todo         <ticket title>
_loose/
  TEAM-1710  Backlog      Fix statusline color threshold

stale (in local fs, not in this sync): TEAM-1650
```
