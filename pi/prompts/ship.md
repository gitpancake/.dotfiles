---
description: Commit, push, open/update PR, and optionally trigger review.
argument-hint: [PR number/URL for review-only]
---

# /ship $ARGUMENTS

Ship the current branch. Use Pi tools directly. Do not push, create PRs, or comment on PRs until the pre-flight state is clear.

If `$ARGUMENTS` contains a PR number or URL, skip commit/push/create and jump to review-only.

## 0. Pre-flight

Run and cache:

- `git status --porcelain=v1 --branch`
- `git branch --show-current`
- `git rev-parse --abbrev-ref --symbolic-full-name @{u}` (allow failure)
- `git log --oneline origin/main..HEAD` (allow failure if no origin/main)
- `git diff --stat origin/main...HEAD` (allow failure if no origin/main)
- `gh pr view --json number,url,state,title 2>/dev/null` (allow failure)

Stop and ask/report if:

- branch is `main` or `master`
- no commits ahead, clean tree, and no existing PR
- unrelated dirty user changes are present

## 1. Commit dirty intended changes

If dirty, inspect the diff. Stage explicit paths only; never blind `git add -A` unless every changed file is intended.

Commit with a conventional subject <=50 chars. Body only when the why is not obvious. Never bypass hooks. If hooks fail, fix root cause and make a new commit; do not amend unless the user asks.

Clean with commits ahead: skip to push.

## 2. Push

Run `git push -u origin HEAD`.

If rejected, use `git pull --rebase` only when the state is straightforward. Surface conflicts and stop rather than silently resolving.

## 3. Optional local ticket / Linear link

If this repo uses `~/.dotfiles/scripts/linear-ticket.py` and a local brief is found for the branch, reuse its existing `linear:` frontmatter.

If no linked ticket exists, create one only through the authorized command:

```bash
LINEAR_TICKET_CREATE_OK=1 ~/.dotfiles/scripts/linear-ticket.py create \
  --team "Autonomy Eng" \
  --title "<action-oriented title, no [AE-] prefix>" \
  --state "In Progress" \
  --assignee me \
  --auto-body origin/main
```

If this fails, continue without a Linear prefix. Do not block shipping on tracker failure.

## 4. PR body

Use existing `.github/PULL_REQUEST_TEMPLATE.md` if present. Otherwise:

```md
## Changed
- <structural change>

## Preserved
- <load-bearing behavior unchanged>

## Test plan
- [ ] <verification step>
```

Rules:

- One-line bullets.
- No generated-by footer.
- Derive from cached commit log and diff stat.
- Include `Linear: <url>` only when an ID/url is known.

Create PR with `gh pr create`. Title <=70 chars; prefix `[AE-NNNN]` only when known.

## 5. Review

Tix project rule: only `cartage-agent` has Claude reviews. For tix tasks in any other repo, do not trigger `@claude review`; skip review and say the repo has no Claude review convention.

For non-tix repos, trigger only the repo's current review convention. Inspect recent PR comments or repo docs before assuming a bot name.

Common choices:

- No bot: skip review trigger and say so.
- `cartage-agent`: `gh pr comment <PR> --body "@claude review"`.
- Repo-specific non-Claude bot: use the exact repo convention.
- Human review: leave the PR ready and report the URL.

Do not wait for asynchronous review results unless the user asks.

## 6. Report and stop

Report:

- PR URL
- Review trigger status
- Tests/checks run

Do not auto-fix after shipping. If you spot a tiny issue, name the exact fix and wait for `go`.
