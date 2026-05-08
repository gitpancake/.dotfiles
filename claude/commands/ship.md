---
description: Commit + push + open a PR with a tight bullet body, then run a full PR review and report findings. Idempotent — re-run on an existing PR to just review.
argument-hint: [optional: PR number or URL to skip create and review-only]
---

# /ship $ARGUMENTS

user's house pattern is: commit → push → PR → review → report. He explicitly likes a body that is **just two bullet lists** (Changed structurally / Preserved) plus a test plan, "and not much else." Don't editorialize.

This command orchestrates existing tooling. Do not re-implement what skills already do — delegate.

## 0. Pre-flight (parallel)

Run these in parallel before doing anything destructive:

- `git status --porcelain` — detect uncommitted changes
- `git branch --show-current` — current branch
- `git rev-parse --abbrev-ref --symbolic-full-name @{u}` (allow failure) — upstream tracking
- `git log --oneline @{u}..HEAD 2>/dev/null || git log --oneline origin/main..HEAD` — local commits ahead
- `gh pr view --json number,url,state,title,body 2>/dev/null` — existing PR for this branch
- If `$ARGUMENTS` is non-empty: parse PR number or URL → set `PR_TARGET=$ARGUMENTS`, **skip §1–§4, jump to §5**

**Stop conditions** (report and wait for go):
- Current branch is `main` / `master` → refuse. Tell user which feature branch to switch to.
- Current branch has no commits ahead of upstream AND no uncommitted changes AND no existing PR → nothing to ship; ask what he meant.

## 1. Commit (only if dirty)

If `git status --porcelain` is non-empty:

- If a `caveman:caveman-commit` skill is available, invoke it. Otherwise compose the message yourself:
  - Subject ≤ 50 chars, conventional-commits style (`feat:`, `fix:`, `refactor:`, `chore:`).
  - Body only when the "why" isn't obvious from the diff.
- Stage the changes you intended to ship — never `git add -A` blindly. If unsure what's in scope, ask.
- Never bypass hooks. If pre-commit fails, fix the underlying issue and create a new commit (do not `--amend`).

If clean and there are local commits ahead → skip to §2.

## 2. Push

`git push -u origin HEAD` (sets upstream on first push, no-op after).

If push is rejected (someone else pushed): `git pull --rebase`, resolve, then push again. Surface conflicts to user instead of resolving silently.

## 3. PR body — tight bullet pattern

user's exact preference, from past feedback: "create a PR with really that bullet list and not much else, because that bullet list (what changed structurally, what i preserved) is really great."

If `.github/PULL_REQUEST_TEMPLATE.md` exists in the repo, use it but keep prose minimal — fill its sections with the same bullet style.

Otherwise, body shape:

```
## Changed
- <structural change 1>
- <structural change 2>

## Preserved
- <behavior preserved 1>
- <existing pattern still honored>

## Test plan
- [ ] <verification step 1>
- [ ] <verification step 2>
```

Rules:
- Each bullet 1 line. No paragraphs.
- "Preserved" exists to reassure reviewers the blast radius is small. List load-bearing behaviors that didn't change.
- "Test plan" lists what a reviewer can run / check. If the project has a precheck.sh, the local checks count.
- No emoji. No "Generated with Claude Code" footer unless project convention requires it.

Derive bullets from `git log --oneline origin/main..HEAD` and the diff (`git diff origin/main...HEAD --stat` for surface area, full diff for detail). Don't restate the diff — abstract.

## 4. Create PR

Use `gh pr create` with:
- `--title`: ≤70 chars, action-oriented, prefixed with Linear ID if branch matches `^[a-z]+/[a-z]+-\d+`. Example: `[TEAM-1530] Refactor Shopify webhook for isTestEnv()`.
- `--body`: from §3, via heredoc to preserve formatting.
- `--base`: usually `main`. If branch is named `feature/<x>-slice-N` or `henry/<x>-slice-N`, base may be the parent feature branch — infer from `git log --oneline` and confirm if ambiguous.
- `--draft`: only if the branch has obviously-incomplete work (TODO commits, failing local checks).

Capture the resulting URL.

### Linear sync (if applicable)

If the branch has a Linear ID:
- `mcp__linear-server__save_comment` on the ticket: `"PR open: <url>. Running review."`
- `mcp__linear-server__update_issue`: state → "In Review" if it's currently "In Progress".

Don't ask first — this matches user's standard flow.

## 5. Run a full review

Now invoke a real review. Pick the best available, in priority order:

1. `pr-review-toolkit:review-pr` skill (preferred — multi-agent comprehensive review)
2. `code-review:code-review` skill
3. Project-level `/code-review` slash command if it exists (example-org-agent has one — defer to it)
4. Fallback: dispatch a `bugfinder` subagent with the PR diff as scope

Pass the PR URL / number explicitly. Wait for the review to finish.

## 6. Report — terse, actionable

Output shape user wants. No preamble.

```
PR: <url>
Linear: <ticket URL or "—">
Review: <skill name used>

## Findings

| # | Severity | File:Line | Summary | Suggested fix |
|---|----------|-----------|---------|----------------|
| 1 | blocker  | src/foo.ts:42 | Null deref on `user.email` | Add guard before `.toLowerCase()` |
| 2 | major    | … | … | … |
| 3 | minor    | … | … | … |
| 4 | NB       | … | … | … |

## Self-check ran
- typecheck: <pass/fail>
- precheck.sh: <pass/fail/n-a>
- tests: <pass/fail/skipped>
```

Severity rubric:
- **blocker** — must fix before merge (correctness, security, data loss, regression)
- **major** — should fix before merge (perf cliff, error-handling hole, contract violation)
- **minor** — nice to fix (naming, dead code, small refactor)
- **NB** — non-blocking observation, no action expected

Skip the table if the review found nothing — say "Review clean. Self-check ran clean." in one line.

## 7. Stop

Do not auto-fix. Do not amend the PR description. Do not request reviewers. user decides what to do with the findings — that's the whole point.

If the review surfaced a blocker that's a single-character fix (typo, obvious null guard), call it out **first** with the exact fix, but still wait for "go" before editing.

## ExampleCorp-specific augmentations (if working in example-org-agent)

When reviewing, weight these higher. Findings here become blockers, not minors:

- `console.log` instead of structured Axiom logger
- Generic `catch (error)` that swallows specific messages
- New positional primitives in function signatures (object-params rule)
- Sentry threshold raised or filtered
- New direct llm-vendor / llm-observability calls (must go through llm-gateway)
- `bun test` not used (just `bun test` is wrong inside worktrees)
- Trigger.dev task added to `TaskRegistry` but not `TASK_ROUTES_ENV` (or vice versa)
- Customer-name / email leak in tests without scrubbing
