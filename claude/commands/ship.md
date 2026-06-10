---
description: Commit + push + open PR + trigger repo-appropriate review. Pass PR# for review-only.
argument-hint: [optional: PR number or URL to skip create and review-only]
model: sonnet
---

# /ship $ARGUMENTS

Commit → push → PR → trigger repo-appropriate review. PR body chooses **small** or **rich**
shape from diff size/risk. Meaningful code PRs include Changed / Preserved + tests. Work lives
in repo + local ticket tree.

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

## 3. PR body — choose sparse vs rich deliberately

If `.github/PULL_REQUEST_TEMPLATE.md` exists, fill its sections with the shape below.
Default to the rich shape when reviewers need context; sparse bodies are only for obviously
small, single-purpose changes.

### Small PR shape

Use only when the branch touches a few files and does not add/change providers, external APIs,
schemas, workflows, routing, auth, persistence, observability, or multi-subsystem behavior.

```
Linear: https://linear.app/<workspace>/issue/AE-NNNN

## Summary

### Changed
- <structural change>

### Preserved
- <load-bearing behavior unchanged>

## Tests
- <verification step and result>
```

### Large / platform / integration PR shape

Use when the diff adds or changes integrations, providers, external APIs, schemas, workflows,
routing, auth, persistence, observability, generated tests, or crosses multiple subsystems.

```
## Linear ticket

[AE-NNNN](https://linear.app/<workspace>/issue/AE-NNNN)

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

Rules: "Preserved" reassures reviewers blast radius is small. Keep bullets one line where
practical; allow short phrases for test coverage and manual blockers. List new/changed test
files separately from commands for non-trivial diffs. No emoji, no generated-with footer unless
repo convention. Derive bullets from the **cached** `LOG_LINES` + `DIFF_STAT` from §0 — don't
re-run git. Abstract, don't restate.

Then `gh pr create`:
- `--title`: `$AE_ID` non-empty → `[AE-NNNN] <desc>` (≤70 chars total).
  Empty → action-oriented title, no ID prefix.
- `--body` from shape above via heredoc.
- `--base` usually `main`; for `*/slice-N` branches infer parent from `git log`, confirm
  if ambiguous.
- `--draft` only if obviously incomplete (TODO commits, failing local checks).

Capture URL.

## 4. Trigger review

Chuck (Railway PR reviewer) reviews PRs in the repos wired to his webhook + allowlist:
`cartage-ai/cartage-agent` and `cartage-ai/ai-employees`. For a PR in either, tag Chuck:

```
gh pr comment "$PR_NUM" --body "@chuck-noland-cartage review"
```

Chuck reacts 👀 on the comment within ~1s, then posts his review in ~2–3 min, once per PR
(loop-guarded). **Format: a single issue comment from `chuck-noland[bot]` on the PR
conversation — body starts `**Chuck finished …**` followed by a review section whose
header varies (`### Review — <title>`, `### Chuck review`); match on author + that opener,
never the header. 🔴 findings are blockers, "Advisory" items are nits** — he creates
no GitHub Review object, no inline review comments, and never touches `reviewDecision`.
Anything polling for his review must read `issues/<PR>/comments` (author
`chuck-noland[bot]`), not `reviews`/`reviewDecision`/`pulls/<PR>/comments`. /ship itself
does not wait — but in a `wt` lane the lane then owns the feedback loop (poll → address
all findings blockers→nits → push → `lane-done.sh`) per its kickoff prompt. For repos
outside that set, skip review and report no convention.

## 5. Report — terse

```
PR: <url>
Review: <triggered via @chuck-noland-cartage review for <repo> | skipped: Chuck does not review this repo>
```

Clean nothing-to-do → say so in one line.

## 6. Stop

Cockpit sessions only: do not auto-fix. Do not amend the PR description. Do not request
reviewers. User decides. Single-character blocker spotted (typo, obvious null guard) →
call out exact fix, still wait for "go" before editing.

In a `wt` lane, /ship returning is NOT the end of the lane — the lane continues into the
review-feedback loop (wait for the review, address every finding, push, `lane-done.sh`)
per its kickoff prompt and global CLAUDE.md §Autonomous semantics.
