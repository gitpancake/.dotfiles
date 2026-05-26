---
description: Commit + push + open PR + trigger @claude review. Pass PR# to re-trigger only.
argument-hint: [optional: PR number or URL to skip create and review-only]
---

# /ship $ARGUMENTS

Commit → push → PR → trigger review. PR body = **two bullet lists** (Changed / Preserved)
+ test plan. No editorializing. Work lives in repo + local ticket tree.

## 0. Pre-flight (parallel)

Parse `$ARGUMENTS`: non-empty token → PR number/URL → `PR_TARGET=<x>`, **skip §1–§3,
jump §4**.

Run in parallel and cache outputs — §2.5 + §3 reuse, never re-run:
- `git status --porcelain`
- `git branch --show-current`
- `git rev-parse --abbrev-ref --symbolic-full-name @{u}` (allow failure)
- `git log --oneline origin/main..HEAD` → `LOG_LINES`
- `git diff --stat origin/main...HEAD` → `DIFF_STAT`
- `gh pr view --json number,url,state,title 2>/dev/null`

**Stop conditions** (report, wait):
- On `main`/`master` → refuse.
- No commits ahead AND clean AND no PR → ask what was meant.

## 1. Commit (only if dirty)

Conventional-commit subject ≤50 chars (`feat:`/`fix:`/`refactor:`/`chore:`/etc.). Body only
when "why" isn't obvious from the diff. Stage explicitly — never `git add -A` blind. Unsure
→ ask. Never bypass hooks. Pre-commit fails → fix root cause, new commit, no `--amend`.

Clean + commits ahead → skip to §2.

## 2. Push

`git push -u origin HEAD`. Rejected → `git pull --rebase`, resolve, push again. Surface
conflicts; don't resolve silently.

## 2.5. Linear ticket (always linked)

Every PR carries `[AE-NNNN] <desc>` so it links to a ticket with description, reasoning,
implementation, assignee.

1. **Resolve brief** from current branch. Reuse `wt --resolve` if available; else
   `grep -rlE "^linear:" "${TICKETS_DIR:-$HOME/.claude/tickets}" --include='*.md'` matched
   by branch slug in filename or `## Local notes`. Found → `BRIEF_FILE=<path>`.
2. **Read `linear:` frontmatter** from `$BRIEF_FILE` (if any). Non-empty → `AE_ID=<that>`,
   **skip to §3**.
3. **No linked ticket** → create one. Script composes body itself from git — do NOT build
   description/reasoning/implementation bullets here, do NOT pass `--description`:
   ```
   LINEAR_TICKET_CREATE_OK=1 ~/.dotfiles/scripts/linear-ticket.py create \
     --team "Autonomy Eng" \
     --title "<≤80 chars, action-oriented, no [AE-] prefix — Linear adds its own ID>" \
     --state "In Progress" \
     --assignee me \
     --auto-body origin/main \
     --labels "<from brief frontmatter labels:, comma-sep — omit flag if none>"
   ```
   `--auto-body origin/main` triggers the script's `compose_body_from_git`: dedup subjects
   → Description, commit `%b` paragraphs → Reasoning, `git diff --stat` grouped by top-dir
   → Implementation. `state` = `In Progress` because work is done (PR is the deliverable).
   stdout on success: `AE-NNNN<TAB>url`.
4. **Capture `AE-NNNN`** from stdout → `AE_ID`. Brief exists → write `linear: AE-NNNN` back
   into its frontmatter so future runs reuse. Brief missing → skip writeback.
5. **Script failure** (nonzero exit: no key, network, team not found) → reason on stderr.
   Log one line, set `AE_ID=""`, continue with no-prefix title. Don't block ship.

## 3. PR body — tight bullet pattern

If `.github/PULL_REQUEST_TEMPLATE.md` exists, fill its sections with this bullet style.
Default shape (prepend `Linear:` line only when `$AE_ID` non-empty):

```
Linear: https://linear.app/<workspace>/issue/AE-NNNN

## Changed
- <structural change>

## Preserved
- <load-bearing behavior unchanged>

## Test plan
- [ ] <verification step>
```

Rules: one-line bullets, no paragraphs. "Preserved" reassures reviewers blast radius is
small. No emoji, no generated-with footer unless repo convention. Derive bullets from the
**cached** `LOG_LINES` + `DIFF_STAT` from §0 — don't re-run git. Abstract, don't restate.

Then `gh pr create`:
- `--title`: `$AE_ID` non-empty → `[AE-NNNN] <desc>` (≤70 chars total).
  Empty → action-oriented title, no ID prefix.
- `--body` from shape above via heredoc.
- `--base` usually `main`; for `*/slice-N` branches infer parent from `git log`, confirm
  if ambiguous.
- `--draft` only if obviously incomplete (TODO commits, failing local checks).

Capture URL.

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

Do not auto-fix. Do not amend the PR description. Do not request reviewers. User decides.
Single-character blocker spotted (typo, obvious null guard) → call out exact fix, still
wait for "go" before editing.
