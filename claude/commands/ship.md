---
description: Commit + push + open a PR with a tight bullet body, then run a full PR review and report findings. Idempotent — re-run on an existing PR to just review.
argument-hint: [optional: PR number or URL to skip create and review-only]
---

# /ship $ARGUMENTS

user's house pattern: commit → verify → push → PR → review → report. Body is **two bullet lists** (Changed structurally / Preserved) plus a test plan. No editorializing. Delegate to existing skills/subagents; don't reimplement.

## 0. Pre-flight (parallel)

Parse `$ARGUMENTS`:
- `--local` token → `LOCAL_REVIEW=1`. Default 0 = external `@claude review` PR comment (saves session tokens).
- `--deep` token → `DEEP=1` (only meaningful with `--local`).
- Remaining non-empty token → PR number/URL → `PR_TARGET=<x>`, **skip §1–§4, jump to §5**.

Run in parallel:
- `git status --porcelain`, `git branch --show-current`, `git rev-parse --abbrev-ref --symbolic-full-name @{u}` (allow failure), `git log --oneline @{u}..HEAD 2>/dev/null || git log --oneline origin/main..HEAD`, `gh pr view --json number,url,state,title,body 2>/dev/null`.

**Stop conditions** (report, wait):
- On `main`/`master` → refuse.
- No commits ahead AND clean AND no PR → ask what was meant.

## 0.5 Verify gate

Skip if `$ARGUMENTS` non-empty (review-only) or `SHIP_SKIP_VERIFY=1` (print `verify gate: bypassed`).

Gate satisfied when `<wt>/.claude/verify.ok` mtime >= HEAD commit mtime. Otherwise dispatch the `verifier` subagent. Pre-compute and pass:
- Base: `origin/main` (or parent feature branch if branch is `*/slice-N`)
- `CHANGED=$(git diff --name-only $BASE...HEAD)`
- `HUNKS=$(git diff --unified=20 $BASE...HEAD)`
- `ACCEPTANCE=$(grep -A 50 -iE 'acceptance criteria|## what should work' ~/.claude/plans/<TICKET>.md 2>/dev/null | head -80)`

Verifier prompt: "Verify branch `<b>` vs base `<base>`. CHANGED+HUNKS+ACCEPTANCE pre-computed below — do NOT re-run git. Scope reads to CHANGED only; use offset/limit on files >300 lines. Exercise end-to-end. Write `<wt>/.claude/verify.log`; on PASS write `verify.ok` with summary+ISO; on FAIL call `~/.claude/scripts/lane-pause.sh verify <reason>`. Report PASS/FAIL one-liner."

**On PASS** → print `verify gate: PASS — <summary>`, continue.
**On FAIL** → STOP. Print last `=== ===` block of `verify.log` and `verify gate: FAIL — <reason>`. Wait for user.

Re-run `/ship` after a fix; new HEAD mtime invalidates old `verify.ok` automatically. Force re-verify without new commit: `~/.claude/scripts/verify-clean.sh`. Pure-refactor fast-path in verifier is expected — don't second-guess.

## 1. Commit (only if dirty)

If `git status --porcelain` non-empty:
- Prefer `caveman:caveman-commit` skill. Else: conventional-commits subject ≤50 chars; body only when "why" isn't obvious from diff.
- Stage explicitly — never `git add -A` blind. Unsure → ask.
- Never bypass hooks. Pre-commit fails → fix root cause, new commit, no `--amend`.

Clean + commits ahead → skip to §2.

## 2. Push

`git push -u origin HEAD`. Rejected → `git pull --rebase`, resolve, push again. Surface conflicts; don't resolve silently.

## 3. PR body — tight bullet pattern

user's preference: bullet list of "what changed structurally / what was preserved" plus test plan, nothing else.

If `.github/PULL_REQUEST_TEMPLATE.md` exists, fill its sections with this same bullet style.

Default shape:

```
## Changed
- <structural change>

## Preserved
- <load-bearing behavior unchanged>

## Test plan
- [ ] <verification step>
```

Rules: one-line bullets, no paragraphs. "Preserved" reassures reviewers blast radius is small. No emoji, no "Generated with Claude Code" footer unless repo convention. Derive bullets from `git log --oneline origin/main..HEAD` + `git diff origin/main...HEAD --stat`; abstract, don't restate.

## 4. Create PR

`gh pr create`:
- `--title` ≤70 chars, action-oriented, prefix Linear ID if branch matches `^[a-z]+/[a-z]+-\d+` (e.g. `[TEAM-1530] Refactor Shopify webhook`).
- `--body` from §3 via heredoc.
- `--base` usually `main`; for `feature/<x>-slice-N` or `henry/<x>-slice-N`, infer parent from `git log`, confirm if ambiguous.
- `--draft` only if obviously incomplete (TODO commits, failing local checks).

Capture URL.

**Linear sync** (if branch has Linear ID, no need to confirm):
- `mcp__linear-server__save_comment`: `"PR open: <url>. Running review."`
- `mcp__linear-server__update_issue`: state → "In Review" if currently "In Progress".

## 5. Run review

### 5.0 External (default, `LOCAL_REVIEW=0`)

```
gh pr comment "$PR_NUM" --body "@claude review"
```

Skip 5.1–5.4. Report per §6 external shape. Don't wait.

### 5.1 Local prefetch (`LOCAL_REVIEW=1`)

```
DIFF=$(gh pr diff "$PR_NUM")
DIFF_FILES=$(gh pr view "$PR_NUM" --json files --jq '.files')
DIFF_LOC=$(printf '%s\n' "$DIFF" | grep -cE '^[+-][^+-]' || true)
```

Embed `$DIFF` / `$DIFF_FILES` in every subagent prompt as `<diff>...</diff>` / `<files>...</files>`. Include: *"Diff and file list above are authoritative. Do not re-run `gh pr diff`, `gh pr view`, or `git diff`."*

### 5.2 Depth

`DEEP=1` (fan-out) when: `$DEEP` set OR `$DIFF_LOC > 500` OR changed paths touch `src/server/db/schema/`, prompts (`*/prompts/*`, `*/knowledge/*`, `customerPrompts/*`, `agents/*/config.ts`), or auth (`TokenService.ts`, `src/lib/auth/`). Else `DEEP=0`.

### 5.3 Single-pass (`DEEP=0`)

Try in order: project `/code-review` → `code-review:code-review` skill → `pr-review-toolkit:code-reviewer` subagent → `bugfinder` subagent (scope = prefetched diff).

### 5.4 Fan-out (`DEEP=1`)

Classify from `$DIFF` / `$DIFF_FILES`: `touches_tests` (`*.test.ts` / `__tests__/`), `touches_errors` (`+` lines with `try {` / `catch (` / `throw `), `touches_types` (`+` lines `^(export )?(type|interface) `), `touches_prompts` (paths above).

Spawn in parallel (one message, multiple Agent calls):

| Specialist | When |
|---|---|
| `pr-review-toolkit:code-reviewer` | always |
| `pr-review-toolkit:pr-test-analyzer` | `touches_tests` |
| `pr-review-toolkit:silent-failure-hunter` | `touches_errors` |
| `pr-review-toolkit:type-design-analyzer` | `touches_types` |
| project `/code-review` | `touches_prompts` |

`pr-review-toolkit` plugin must be enabled in `~/.claude/settings.json` — disabled by default for token cost; re-enable before `--local --deep`.

## 6. Report — terse

### External (`LOCAL_REVIEW=0`)

```
PR: <url>
Linear: <ticket URL or "—">
Review: triggered externally via @claude review (results in PR comments, ~2-5min)

## Self-check ran
- typecheck: <pass/fail>
- precheck.sh: <pass/fail/n-a>
- tests: <pass/fail/skipped>
```

### Local (`LOCAL_REVIEW=1`)

```
PR: <url>
Linear: <ticket URL or "—">
Review: <skill name used>

## Findings

| # | Severity | File:Line | Summary | Suggested fix |
|---|----------|-----------|---------|----------------|
| 1 | blocker  | src/foo.ts:42 | Null deref on `user.email` | Add guard before `.toLowerCase()` |

## Self-check ran
- typecheck: <pass/fail>
- precheck.sh: <pass/fail/n-a>
- tests: <pass/fail/skipped>
```

Severity: **blocker** (must fix — correctness/security/data-loss/regression) · **major** (should fix — perf cliff/error hole/contract violation) · **minor** (nice — naming/dead code) · **NB** (observation).

Clean review → "Review clean. Self-check ran clean." one line.

## 7. Stop

Do not auto-fix. Do not amend PR description. Do not request reviewers. user decides.

Single-character blocker (typo, obvious null guard) → call out first with exact fix, still wait for "go" before editing.

## ExampleCorp-agent — local review only

In `example-org-agent` with `--local`, also weight rules from `~/.claude/org/example-org/code-review-augment.md` as blockers.
