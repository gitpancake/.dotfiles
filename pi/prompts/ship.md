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

## 3. Required local ticket / Linear link

Every shipped PR must have a real Linear issue and link. No placeholder IDs (`ENG-`, `AE-`, `XXXX`) and no `N/A` ticket sections.

If this repo uses `~/.dotfiles/scripts/linear-ticket.py` and a local brief is found for the branch:

- Reuse its existing `linear:` frontmatter only when it is a real identifier like `AE-2048`.
- If the frontmatter is empty, YAML/object-shaped metadata, or otherwise not a real identifier, create a new ticket.
- After creating a ticket, update the local brief frontmatter to `linear: AE-NNNN`.

If no linked ticket exists, create one only through the authorized command:

```bash
LINEAR_TICKET_CREATE_OK=1 ~/.dotfiles/scripts/linear-ticket.py create \
  --team "Autonomy Eng" \
  --title "<action-oriented title, no [AE-] prefix>" \
  --state "In Progress" \
  --assignee me \
  --auto-body origin/main
```

If ticket creation fails, stop and report the failure. Do not create or update a PR without a real Linear link unless the user explicitly says to ship without Linear.

## 4. PR body

Use existing `.github/PULL_REQUEST_TEMPLATE.md` if present. Otherwise choose a body shape from the cached commit log and diff stat.

Use the **small PR** shape only when the branch is narrowly scoped: a few files, no new integration/provider/workflow/schema surface, and no reviewer needs blast-radius reassurance.

```md
Linear: <url>

## Summary

### Changed
- <structural change>

### Preserved
- <load-bearing behavior unchanged>

## Tests
- <verification step and result>
```

Use the **large / platform / integration PR** shape when the diff adds or changes providers, external APIs, schemas, workflows, routing, auth, persistence, observability, generated tests, or crosses multiple subsystems.

```md
## Linear ticket

[AE-NNNN](<url>)

## Summary

### Changed
- <new capability or interface>
- <wiring / schema / workflow change>
- <operational behavior change>

### Preserved
- <existing behavior intentionally unchanged>
- <compatibility / default / fallback behavior>
- <blast-radius limit or no-new-dependency/index/migration note>

## Automated tests added

- `<test file>` — <behavior covered>.

## Manual testing steps

- `<command>` ✅
- `<command>` ⚠️ <known existing failure or credential/staging blocker>
- <post-credential or production smoke step, if applicable>
```

Rules:

- Prefer the large shape for anything reviewers may need to reason about; sparse PR bodies are only for obviously small changes.
- Keep bullets one line where practical; allow short explanatory phrases for test coverage and manual blockers.
- Always include `Changed` and `Preserved` for meaningful code changes.
- List new/changed test files separately from commands when the diff is non-trivial.
- No generated-by footer.
- Derive from cached commit log and diff stat.
- Include the Linear issue URL in the template's `## Linear ticket` section, or `Linear: <url>` when no template exists.
- Never leave `[ENG-]`, `[AE-]`, `ENG-XXXX`, `AE-XXXX`, or `N/A` in the PR title/body.

Create PR with `gh pr create`. Title <=70 chars; prefix `[AE-NNNN]` using the created/reused ticket ID.

After PR creation, add the PR URL as a Linear comment using:

```bash
printf '%s\n' "PR: <pr-url>" | LINEAR_TICKET_CREATE_OK=1 ~/.dotfiles/scripts/linear-ticket.py comment --id AE-NNNN
```

## 5. Review

Reviews on `cartage-ai/cartage-agent` and `cartage-ai/ai-employees` fire **automatically** on PR open/push — nothing to tag or trigger, and pushing new commits is the re-review request. (Chuck is retired: never tag `@chuck-noland-cartage`, never poll for `chuck-noland[bot]` comments.)

- **Devin** (`devin-ai-integration[bot]`) and **Codex** post normal GitHub Review objects with inline comments (`pulls/<PR>/comments`).
- Repos with `.github/workflows/arbiter.yml` (e.g. `cartage-agent`) also get a REQUIRED `arbiter` commit status on the head sha (`approve`=success, `block`/`needs-human`=failure). Read it with:

```bash
gh api repos/{owner}/{repo}/commits/<head-sha>/status --jq '.statuses[] | select(.context=="arbiter")'
```

For other repos, trigger only the repo's current review convention. Inspect recent PR comments or repo docs before assuming a bot name.

Common choices:

- No bot: skip review trigger and say so.
- Repo-specific bot: use the exact repo convention.
- Human review: leave the PR ready and report the URL.

Do not wait for asynchronous review results unless the user asks.

## 6. Report and stop

Report:

- PR URL
- Review trigger status
- Tests/checks run

Do not auto-fix after shipping. If you spot a tiny issue, name the exact fix and wait for `go`.
