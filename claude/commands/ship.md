---
description: Commit + push + open PR + trigger @claude review. Pass PR# to re-trigger only.
argument-hint: [optional: PR number or URL to skip create and review-only]
model: claude-opus-4-7
---

# /ship $ARGUMENTS

Commit → push → PR → trigger review. Body is **two bullet lists** (Changed / Preserved)
plus a test plan. No editorializing. Work lives entirely in the repo + the local ticket
tree — nothing syncs anywhere.

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

## 2.5. Linear ticket (create if absent)

Goal: every PR carries `[AE-NNNN] <desc>` so it links to a ticket with description,
reasoning, implementation, and assignee.

1. **Resolve brief** from current branch. Reuse `wt --resolve` if available; else
   `grep -rlE "^linear:" "${TICKETS_DIR:-$HOME/.claude/tickets}" --include='*.md'` and match by branch slug
   in filename or `## Local notes`. Found → `BRIEF_FILE=<path>`.
2. **Read `linear:` frontmatter** from `$BRIEF_FILE` (if any). Non-empty → `AE_ID=<that>`,
   **skip to §3**.
3. **No brief found** → prompt: `No local brief for this branch — create Linear from
   commits+diff anyway? [Y/n]`. `n` → set `AE_ID=""`, skip to §3 with classic no-prefix
   title. `y` (default) → proceed.
4. **Compose body** from real data — never invent:
   - **Description**: bullets from `git log --format='%s' origin/main..HEAD`, deduped.
   - **Reasoning**: brief's `## Context` section verbatim if present; else commit-body
     paragraphs (`git log --format='%b' origin/main..HEAD`) trimmed of empties.
   - **Implementation**: file-list summary from `git diff --stat origin/main...HEAD` —
     group by top-level dir, one line per group with file count + paths.
5. **Create the ticket** via the local script — no MCP. (`scripts/linear-ticket.py` hits
   the Linear GraphQL API directly with `$LINEAR_API_KEY`; this keeps the Linear tool
   schemas out of every lane's context — the tax that made `/ship` expensive.) Write the
   step-4 body to a temp file, then run:
   ```
   cat > "${TMPDIR:-/tmp}/ship-linear-body.md" <<'BODY'
   ## Description
   <bullets>

   ## Reasoning
   <paragraphs or brief Context>

   ## Implementation
   <grouped file summary>
   BODY
   ~/.dotfiles/scripts/linear-ticket.py create \
     --team "Autonomy Eng" \
     --title "<≤80 chars, no [AE-] prefix — Linear adds its own ID>" \
     --state "In Progress" \
     --assignee me \
     --labels "<brief frontmatter labels:, comma-sep — omit flag if none>" \
     --description-file "${TMPDIR:-/tmp}/ship-linear-body.md"
   ```
   `state` = `In Progress` because work is done at this point (PR is the deliverable).
   stdout on success is `AE-NNNN<TAB>url`.
6. **Capture `AE-NNNN`** from the script's stdout → `AE_ID`. Write back into brief
   frontmatter (`linear: AE-NNNN`) so future runs reuse it. Brief missing → skip writeback.
7. **Script failure** (nonzero exit: no key, network, team not found) → it prints the
   reason to stderr. Log it in one line, set `AE_ID=""`, continue with no-prefix title.
   Do not block ship.

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

Rules: one-line bullets, no paragraphs. "Preserved" reassures reviewers the blast radius
is small. No emoji, no generated-with footer unless repo convention. Derive bullets from
`git log --oneline origin/main..HEAD` + `git diff origin/main...HEAD --stat` — abstract,
don't restate.

Then `gh pr create`:
- `--title`: `$AE_ID` non-empty → `[AE-NNNN] <desc>` (≤70 chars total).
  Empty → action-oriented title with no ID prefix.
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

Do not auto-fix. Do not amend the PR description. Do not request reviewers. User decides.
Single-character blocker spotted (typo, obvious null guard) → call it out with the exact
fix, still wait for "go" before editing.
