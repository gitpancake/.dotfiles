---
description: Commit + push + open a PR with a tight bullet body, then run a full PR review and report findings. Idempotent — re-run on an existing PR to just review.
argument-hint: [optional: PR number or URL to skip create and review-only]
---

# /ship $ARGUMENTS

user's house pattern is: commit → push → PR → review → report. He explicitly likes a body that is **just two bullet lists** (Changed structurally / Preserved) plus a test plan, "and not much else." Don't editorialize.

This command orchestrates existing tooling. Do not re-implement what skills already do — delegate.

## 0. Pre-flight (parallel)

Parse `$ARGUMENTS` first:
- Strip the token `--deep` if present and set `DEEP=1`. Without `--deep`, `DEEP=0`.
- The remainder, if non-empty, is a PR number / URL → `PR_TARGET=<remainder>`, **skip §1–§4, jump to §5**.

Then run these in parallel before doing anything destructive:

- `git status --porcelain` — detect uncommitted changes
- `git branch --show-current` — current branch
- `git rev-parse --abbrev-ref --symbolic-full-name @{u}` (allow failure) — upstream tracking
- `git log --oneline @{u}..HEAD 2>/dev/null || git log --oneline origin/main..HEAD` — local commits ahead
- `gh pr view --json number,url,state,title,body 2>/dev/null` — existing PR for this branch

**Stop conditions** (report and wait for go):
- Current branch is `main` / `master` → refuse. Tell user which feature branch to switch to.
- Current branch has no commits ahead of upstream AND no uncommitted changes AND no existing PR → nothing to ship; ask what he meant.

## 0.5 Verify gate

Type-check green is necessary but not sufficient. Before any commit / push / PR, the lane must produce evidence the change actually works end-to-end. Skip this entire section if `$ARGUMENTS` is non-empty (review-only mode) or if `SHIP_SKIP_VERIFY=1` is set.

### Bypass

`SHIP_SKIP_VERIFY=1 /ship` skips this section entirely — for use when user has already verified manually. Print one line: `verify gate: bypassed (SHIP_SKIP_VERIFY=1)` and continue to §1.

### Find the right .claude/ directory

```
WT_ROOT=$(git rev-parse --show-toplevel)
VERIFY_OK="$WT_ROOT/.claude/verify.ok"
VERIFY_LOG="$WT_ROOT/.claude/verify.log"
```

### Decide whether to dispatch

The gate is satisfied when `verify.ok` exists AND is newer than every file modified by the latest commit. Compute:

```
HEAD_MTIME=$(git log -1 --format=%ct HEAD)
OK_MTIME=$(stat -f %m "$VERIFY_OK" 2>/dev/null || stat -c %Y "$VERIFY_OK" 2>/dev/null || echo 0)
```

- `verify.ok` missing → dispatch.
- `OK_MTIME < HEAD_MTIME` → stale, dispatch.
- `OK_MTIME >= HEAD_MTIME` → fresh, **skip dispatch**, print `verify gate: fresh (verify.ok @ <iso>)`, proceed to §1.

This makes the gate idempotent: each new commit invalidates a prior PASS by mtime, forcing re-verification.

### Dispatch the verifier subagent

Resolve the diff base first:
- Default: `origin/main`.
- If branch matches `*/slice-N` off a feature branch (confirm from `git log --oneline`), use the parent feature branch.

Then **pre-compute the verification scope** (saves the verifier from re-running git):

```bash
BASE=<resolved base>
CHANGED=$(git diff --name-only "$BASE"...HEAD)
HUNKS=$(git diff --unified=20 "$BASE"...HEAD)
ACCEPTANCE=$(grep -A 50 -iE 'acceptance criteria|## what should work' "$HOME/.claude/plans/<TICKET>.md" 2>/dev/null | head -80)
```

Use the Agent tool, `subagent_type: "verifier"`, with this prompt:

> Verify the changes on this branch end-to-end.
> Branch: `<current-branch>`. Base: `<resolved base>`.
>
> Changed files (already computed — do NOT re-run `git diff`):
> ```
> <CHANGED>
> ```
>
> Diff hunks (already computed):
> ```
> <HUNKS>
> ```
>
> Acceptance criteria from the plan (if present):
> ```
> <ACCEPTANCE — empty string if no plan>
> ```
>
> Scope your `Read` calls to ONLY the files in CHANGED. For files >300 lines, use `Read` with `offset`/`limit` around the hunk line numbers. Do not read unrelated files.
>
> Exercise the changes (UI in browser, API via curl, DB via real query, worker via real enqueue) and write evidence to `<wt>/.claude/verify.log`. On PASS, write `<wt>/.claude/verify.ok` with a one-line summary + ISO timestamp. On FAIL, do not write `verify.ok` — tag the lane via `~/.claude/scripts/lane-pause.sh verify "<reason>"`.
>
> Report PASS / FAIL with a one-line summary.

Wait for the subagent to finish.

### On verifier PASS

Print one line:

```
verify gate: PASS — <subagent's one-line summary>
```

Continue to §1.

### On verifier FAIL

**STOP.** Do not commit, do not push, do not open a PR. Surface the tail of `verify.log` (the last `=== ... ===` block) and the failure reason. Print:

```
verify gate: FAIL — <reason>
log: <wt>/.claude/verify.log
```

user's `agent-board.sh` will already show `WAITING:verify:<reason>` because the subagent called `lane-pause.sh`. Wait for user's instruction.

### Pure refactor fast path

If the verifier classifies the diff as pure refactor and the test suite passes, it can PASS quickly without dev-server / curl gymnastics. That's expected — don't second-guess.

### Re-running /ship after a fix

After user fixes the issue and lands a new commit, just re-run `/ship`. The new commit's mtime invalidates the old `verify.ok` (or there was no `verify.ok` to begin with), so the gate re-dispatches automatically. No manual cleanup needed. To force re-verification without a new commit, run `~/.claude/scripts/verify-clean.sh`.

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

Default = single-pass via the project-tuned `/code-review`. Multi-agent fan-out is opt-in (`--deep`) or auto-triggered for large / risky PRs. Both paths get the diff prefetched once and embedded in subagent prompts — subagents must not re-fetch.

### 5.0 Prefetch the diff once

```bash
PR_NUM=<from §0 or §4>
DIFF=$(gh pr diff "$PR_NUM")
DIFF_FILES=$(gh pr view "$PR_NUM" --json files --jq '.files')
DIFF_LOC=$(printf '%s\n' "$DIFF" | grep -cE '^[+-][^+-]' || true)
```

Treat `$DIFF` and `$DIFF_FILES` as the canonical artifacts for §5.2 / §5.3. Embed them in every subagent prompt via:

```
<diff>
$DIFF
</diff>

<files>
$DIFF_FILES
</files>
```

Subagent prompts must include the line: *"The diff and file list above are authoritative. Do not run `gh pr diff`, `gh pr view`, or `git diff` — read the embedded artifacts."*

### 5.1 Choose review depth

Set `DEEP=1` (multi-agent fan-out) when ANY of:
- `$DEEP` was set in §0 (`--deep` flag)
- `$DIFF_LOC > 500`
- changed paths touch `src/server/db/schema/`, prompts (`*/prompts/*`, `*/knowledge/*`, `customerPrompts/*`, `agents/*/config.ts`), or auth (`src/server/services/TokenService.ts`, `src/lib/auth/`)

Otherwise `DEEP=0` → §5.2.

### 5.2 Single-pass path (default)

Invoke the example-org-tuned project review and stop:

- If a project `/code-review` slash command exists in `.claude/commands/code-review.md`, invoke it via the Skill tool, passing the PR number and the prefetched `<diff>` / `<files>` blocks.
- Otherwise fall back to the `code-review:code-review` skill, then to `pr-review-toolkit:code-reviewer` as a single subagent (NOT the full fan-out).

One review pass. Aggregate findings into §6.

### 5.3 Deep path (fan-out, gated)

Classify the diff once from `$DIFF` / `$DIFF_FILES`:

- `touches_tests` — any path matches `*.test.ts` or `__tests__/`
- `touches_errors` — `+` lines contain `try {`, `catch (`, or `throw `, OR a hunk modifies an existing catch body
- `touches_types` — `+` lines match `^(export )?(type|interface) `
- `touches_prompts` — any path under `prompts/`, `knowledge/`, `customerPrompts/`, or `agents/*/config.ts`

Spawn ONLY matching specialists, in parallel (single message, multiple Agent tool uses):

| Specialist | Spawn when |
|---|---|
| `pr-review-toolkit:code-reviewer` | always |
| `pr-review-toolkit:pr-test-analyzer` | `touches_tests` |
| `pr-review-toolkit:silent-failure-hunter` | `touches_errors` |
| `pr-review-toolkit:type-design-analyzer` | `touches_types` |
| project `/code-review` (prompt-quality checklist) | `touches_prompts` |

Each subagent prompt embeds the prefetched `<diff>` / `<files>` blocks and the no-refetch line. Wait for all to finish; aggregate into §6.

### 5.4 Fallback

If neither §5.2 nor §5.3 path is available, dispatch a `bugfinder` subagent with the prefetched diff as scope.

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
