---
description: Pick up an epic and spawn an autonomous Ralph lane — accepts a single epic brief OR a folder of child tickets, which it orders into a story list first.
argument-hint: <EPIC|EPIC-FOLDER> <BASE-BRANCH> [extra context...]
---

# /epic $ARGUMENTS

Spawns `wt --ralph` — a lane running the Ralph autonomous loop. Two epic shapes:

- **Single-brief epic** — one brief at `~/.claude/tickets/**/<EPIC>.md`. The lane runs `/prd` → `/ralph` to synthesize its own story list.
- **Folder epic** — a directory `~/.claude/tickets/<EPIC>/` of child ticket `.md` files (e.g. `billing-epic/` with a couple dozen tickets). The decomposition already happened in Linear, so `/epic` runs **one planning pass** to order the children into a `_prd.json` story list — then the lane consumes it directly, no `/prd` / `/ralph` re-synthesis.

Syncs the cockpit to a base branch, folds in any extra context, spawns the lane. Do **not** edit
project source — this command only prepares and spawns.

## 1. Parse

`$ARGUMENTS` = `<EPIC> <BASE> [context...]`:
- **token 1** — `EPIC` (required). A Linear epic ID, `DRAFT-<N>`, or a folder slug under
  `~/.claude/tickets/` (e.g. `billing-epic`). Empty → ask, stop.
- **token 2** — `BASE` (required). Base branch to spawn off. `.` = use the cockpit's
  current branch as-is.
- **rest** — `CONTEXT` (optional). Free-text notes for the lane.

## 2. Locate the epic — two shapes

Resolve `EPIC`, in order:

1. **Single-brief** — `find ~/.claude/tickets -name "<EPIC>.md" -type f`. Hit, and the file is a
   real brief (not a `moved -> ` tombstone) → `SHAPE=brief`, `BRIEF=<that file>`.
2. **Folder** — `~/.claude/tickets/<EPIC>/` is a directory with `.md` children. Or `<EPIC>` is a
   key in `~/.claude/tickets/.epics.json` whose mapped slug dir exists. → `SHAPE=folder`,
   `FOLDER=<that dir>`, `SLUG=<dir basename>`.
3. **Neither** → stop. Tell user: `/sync-from-linear` (real Linear epic) or `/scope`
   (fresh idea) first.

## 3. Sync the cockpit to BASE

Skip if `BASE` == `.`.

```bash
git fetch --quiet origin
git rev-parse --verify "origin/<BASE>"   # missing → stop, report
git checkout "<BASE>"
git merge --ff-only "origin/<BASE>"
```

ff-merge fails (dirty tree / diverged) → stop, surface it. Never force.

## 4a. SHAPE=brief — fold context, spawn

If `CONTEXT` non-empty, append to `BRIEF` under `## Local notes` (create that section at end of
file if missing):

```
### Epic note — <ISO-8601 date>
<CONTEXT>
```

Then spawn:

```bash
wt --ralph <EPIC>
```

The lane: `ralph-bootstrap` → reads `BRIEF` → `/prd` → `/ralph` (→ `scripts/ralph/prd.json`) →
`./scripts/ralph/ralph.sh --tool claude`, one story per fresh-context iteration → `/ship` on
`<promise>COMPLETE</promise>`.

## 4b. SHAPE=folder — planning pass, then spawn

The child tickets *are* the decomposition. Don't re-synthesize — order them.

**Read every child.** All `.md` files directly under `FOLDER`. Skip:
- tombstones — files whose only content is `moved -> ...`
- generated files — anything matching `_*` (e.g. a prior `_prd.json`)

**Order them.** One planning pass over all children. Sequence by dependency: schema / infra /
shared-primitive tickets first, their consumers next, UI / polish / docs last. Use each ticket's
`## Context`, `## Acceptance criteria`, title, and any `parent:` hint. Dedupe tickets that fully
overlap — fold the loser's AC into the winner's `notes`.

**Build `<FOLDER>/_prd.json`.** One child ticket = one story, in dependency order:

```json
{
  "project": "<folder slug>",
  "branchName": "",
  "description": "<one-line epic summary; prepend CONTEXT if non-empty>",
  "userStories": [
    {
      "id": "<TICKET-ID>",
      "title": "<ticket title>",
      "description": "<ticket ## Context, condensed to 1-3 sentences>",
      "acceptanceCriteria": ["<from ticket ## Acceptance criteria, verbatim>", "Typecheck passes"],
      "priority": 1,
      "passes": false,
      "notes": ""
    }
  ]
}
```

- `priority` = 1-based position in the order.
- AC reads "none specified in Linear" → derive 1-2 concrete criteria from the ticket's Context.
  Always include `"Typecheck passes"`.
- `branchName` stays `""` — the lane stamps it from its actual branch.

**Show user the order and confirm.** Print a terse numbered list (`priority  ID  title`) and
ask: spawn the Ralph lane with this order, or stop so he can edit `_prd.json` first? Wait for go.

**Spawn:**

```bash
wt --ralph <SLUG>
```

`wt --ralph <slug>` (a bare slug, not a ticket ID) finds `<FOLDER>/_prd.json`, branches off the
now-current `BASE`, and the lane: `ralph-bootstrap` → copies `_prd.json` → `scripts/ralph/prd.json`
→ stamps `branchName` + tunes `scripts/ralph/CLAUDE.md` test commands → `./scripts/ralph/ralph.sh
--tool claude`, one story per fresh-context iteration → `/ship` on `<promise>COMPLETE</promise>`.
It does **not** run `/prd` or `/ralph` — the story list is already built and ordered.

Branch type defaults to `feature/` — override with `wt --ralph --type <prefix> <SLUG>` directly
instead.

## 5. Report, then stop

> Ralph lane spawned off `<BASE>`. Autonomous epic loop running in new tmux window — <N> stories
> from `<FOLDER or BRIEF>`. This pane is done.

## Stop conditions

- Missing `EPIC` / `BASE`, or epic not found (neither brief nor folder) — ask or report, stop.
- ff-merge failure — surface, stop.
- `SHAPE=folder` and user doesn't confirm the order — stop, leave `_prd.json` for him to edit.
- After spawn — done. Don't follow the lane.
