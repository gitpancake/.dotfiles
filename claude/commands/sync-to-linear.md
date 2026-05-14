---
description: Push completed work to Linear — reads a branch or PR's commits + diff, creates (or closes) one Linear ticket so the team has visibility. Run at end of day.
argument-hint: <branch-name | PR-number> (defaults to current branch)
---

# /sync-to-linear $ARGUMENTS

The **write** half of the Linear boundary. Run at end of day on completed work. Linear is
downstream — it never feeds the work loop, it just records what shipped so the team can see
it and pick projects up where they stand.

## 1. Parse the target

`$ARGUMENTS` → `TARGET`:
- All digits → PR number.
- Non-empty otherwise → branch name.
- Empty → current branch (`git branch --show-current`). On `main`/`master` → ask which
  branch or PR was meant, stop.

## 2. Gather the work (parallel)

**PR number** → `gh pr view <n> --json title,body,url,headRefName,state,commits,files` and
`gh pr diff <n> --stat`.

**Branch** → `git log origin/main..<branch> --oneline`,
`git diff origin/main...<branch> --stat`, and `gh pr list --head <branch> --json number,url`
(a PR may already exist for it).

## 3. Find the existing ticket — don't duplicate

If the branch matches `^[a-z]+/([a-z]+-\d+)`, extract the Linear ID and look for
`~/.claude/tickets/**/<ID>.md`:
- **Found, frontmatter has `id:`** → the ticket already exists in Linear. Go to §4b (update).
- **Not found, or no `id:`** → go to §4a (create).

## 4a. Create a new ticket

`mcp__linear-server__create_issue`:
- **Team**: `AE` (Platform Eng) unless context says otherwise.
- **State**: `Done`.
- **Title**: ≤80 chars, action-oriented, no fluff. Prefix nothing — this is post-hoc.
- **Body** — house style:

```
## Context
<1-3 sentences — what this work was, why it happened>

## Changed
- <structural change, abstracted from the commits — not a commit-log restate>

## References
- PR: <url>
```

Return the new issue URL.

## 4b. Update the existing ticket

- `mcp__linear-server__update_issue <ID>` → state `Done`.
- `mcp__linear-server__save_comment <ID>` → `"Shipped: <PR url>. <one-line summary>."`
- Update the local `~/.claude/tickets/**/<ID>.md` frontmatter `status: Done`.

## 5. Report — terse

```
Linear: <issue url>  (created | updated → Done)
PR:     <url or "—">
```

## 6. Stop

One ticket per invocation. Multiple branches/PRs → user runs this once per target.
Never create tickets for work that isn't complete — that's what the local
`~/.claude/tickets/` files are for.
