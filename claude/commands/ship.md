---
description: Commit + push + open a PR with a tight bullet body, then trigger an external @claude review. Idempotent — pass a PR number to skip create and just re-trigger review.
argument-hint: [optional: PR number or URL to skip create and review-only]
---

# /ship $ARGUMENTS

Commit → push → PR → trigger review. Body is **two bullet lists** (Changed / Preserved)
plus a test plan. No editorializing. Linear is not touched here — completed work reaches
Linear at end of day via `/sync-to-linear`.

## 0. Pre-flight (parallel)

Parse `$ARGUMENTS`: a non-empty token → PR number/URL → `PR_TARGET=<x>`, **skip §1–§3,
jump to §4**.

Run in parallel:
- `git status --porcelain`, `git branch --show-current`,
  `git rev-parse --abbrev-ref --symbolic-full-name @{u}` (allow failure),
  `git log --oneline @{u}..HEAD 2>/dev/null || git log --oneline origin/main..HEAD`,
  `gh pr view --json number,url,state,title 2>/dev/null`.

**Stop conditions** (report, wait):
- On `main`/`master` → refuse.
- No commits ahead AND clean AND no PR → ask what was meant.

## 1. Commit (only if dirty)

If `git status --porcelain` non-empty:
- Prefer the `caveman:caveman-commit` skill. Else: conventional-commit subject ≤50 chars;
  body only when "why" isn't obvious from the diff.
- Stage explicitly — never `git add -A` blind. Unsure → ask.
- Never bypass hooks. Pre-commit fails → fix root cause, new commit, no `--amend`.

Clean + commits ahead → skip to §2.

## 2. Push

`git push -u origin HEAD`. Rejected → `git pull --rebase`, resolve, push again. Surface
conflicts; don't resolve silently.

## 3. PR body — tight bullet pattern

If `.github/PULL_REQUEST_TEMPLATE.md` exists, fill its sections with this bullet style.
Default shape:

```
## Changed
- <structural change>

## Preserved
- <load-bearing behavior unchanged>

## Test plan
- [ ] <verification step>
```

Rules: one-line bullets, no paragraphs. "Preserved" reassures reviewers the blast radius
is small. No emoji, no generated-with footer unless repo convention. Derive bullets from
`git log --oneline origin/main..HEAD` + `git diff origin/main...HEAD --stat` — abstract,
don't restate.

Then `gh pr create`:
- `--title` ≤70 chars, action-oriented. Prefix the Linear ID if the branch matches
  `^[a-z]+/[a-z]+-\d+` (e.g. `[TEAM-1530] Refactor Shopify webhook`).
- `--body` from the shape above via heredoc.
- `--base` usually `main`; for `*/slice-N` branches infer the parent from `git log`,
  confirm if ambiguous.
- `--draft` only if obviously incomplete (TODO commits, failing local checks).

Capture the URL.

## 4. Trigger review

```
gh pr comment "$PR_NUM" --body "@claude review"
```

External review — results land in PR comments in ~2–5 min. Don't wait.

## 5. Report — terse

```
PR: <url>
Review: triggered via @claude review (results in PR comments, ~2-5min)
```

Clean nothing-to-do → say so in one line.

## 6. Stop

Do not auto-fix. Do not amend the PR description. Do not request reviewers. user decides.
Single-character blocker spotted (typo, obvious null guard) → call it out with the exact
fix, still wait for "go" before editing.
