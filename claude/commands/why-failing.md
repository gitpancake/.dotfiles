---
description: Diagnose why a PR's CI is failing — fetch failing checks, build a local repro, root-cause, then report or spawn a fix lane.
argument-hint: <PR number or URL — omit to use the current branch's PR>
---

# /why-failing $ARGUMENTS

Turn "why is CI red on #N" into a root cause. Fetch the failing checks, pull their logs, reproduce the failure **locally** (the diagnose loop's Phase 1 — a red CI run you can't reproduce is a guess), name the cause, then either report or spawn an autonomous fix lane on the PR branch. Diagnosis first; never push a speculative fix.

**Doctrine** (Pragmatic Programmer ch 3, 5, 8):
- **Don't panic** (PP §25). Deadline pressure produces speculative fixes. Slow down.
- **"select" isn't broken** (PP §26). Runner / framework / std lib is almost never the bug. Suspect the PR diff first.
- **Don't assume — prove it** (PP §27). Every hypothesis ships with the probe that would falsify it.
- **Find bugs once** (PP §66). The fix includes a regression test AND a grep for sibling occurrences — bug-classes survive because nobody looked for peers.

## 0. Resolve target

`$ARGUMENTS` = PR number or URL. Empty → resolve the current branch's PR: `gh pr view --json number,headRefName,state` (no arg = current branch). No PR for the branch → ask for a PR number and stop. Extract `PR_NUM`.

## 1. Fetch failing checks (parallel)

- `gh pr checks <PR_NUM>` — every check run + state (pass/fail/pending) + details URL. This is the failure list.
- `gh pr view <PR_NUM> --json number,url,title,state,headRefName,baseRefName,statusCheckRollup` — branch + rollup.

**Stop conditions** (report, wait):
- All checks green / none failing → "CI is green on #<PR_NUM> — nothing failing." Stop.
- Only `pending`/`queued`, none failed → "CI still running, no failures yet." Stop.
- PR `MERGED`/`CLOSED` → note it; diagnose only if the user still wants it.

## 2. Pull failure logs

For each **failed** check, get the actual output — don't guess from the check name:

- GitHub Actions: extract the run ID from the check's details URL → `gh run view <run-id> --log-failed` (only the failed steps). Big logs → grep for the failing test name / `Error`/`FAIL`/`✗`/exit code, targeted read; never dump the whole log into context.
- Non-Actions checks (Vercel, external StatusContext): open the details URL via the rollup; report the provider + state, fetch logs only if reachable by `gh`/`curl`.

## 3. Classify

One failure mode drives the whole approach — name it before reproducing:

| Class | Tell | Local repro |
|---|---|---|
| **build/compile** | tsc/bundler error, import resolution | `bun run build` / typecheck at the failing path |
| **test** | assertion / thrown error in a named test | run that one test file/case locally |
| **lint/format** | eslint/biome/prettier nonzero exit | run the linter on the changed paths |
| **flake** | passes on re-run, timing/order-dependent, network | re-run to confirm non-determinism before "fixing" |
| **infra/CI** | runner OOM, missing secret, checkout/auth fail | not a code bug — report as CI infra, don't patch source |

## 4. Reproduce locally (diagnose Phase 1)

Hand off to the **`diagnose` skill** — the failing CI check is the symptom; build the fast deterministic local loop that reproduces it (the failing test, the build command, the linter on the exact changed files). Confirm the **same** failure mode appears locally before hypothesising. Flake → raise the reproduction rate (loop it) rather than chase a clean repro. Can't reproduce locally → that's the finding (env/secret/runner-specific); say so, list what you tried, don't speculate a code fix.

## 5. Root-cause

State the cause in one line + the `file:line` that owns it. If a recent commit on the branch introduced it, name the commit. Distinguish **"this PR broke it"** from **"main is already red"** — check whether the same check fails on `baseRefName` (`gh pr checks` on a recent base PR, or `git log origin/<base>`); a pre-existing main failure is not this PR's bug.

**Sibling search (find bugs once — PP §66).** Once the cause is named, grep for the same pattern elsewhere in the repo before declaring root-cause complete. A `forEach(async …)` race, a missed `T00:00:00Z` boundary, a stray `as any` on external JSON — these rarely live alone. List sibling sites in the report so the fix slice can either include them or explicitly defer with a ticket. Skipping this is how the same class re-fails CI a week later.

## 6. Report + decide fix

Report: failing checks → classified cause → `file:line` → proposed fix (concrete diff sketch). Then:

- **Trivial + unambiguous** (lint, obvious typo, one-line guard) and you're already in a lane/branch you can push → apply, commit, `/ship <PR_NUM>` for re-review.
- **Non-trivial, or in the cockpit (not a lane)** → offer to spawn an autonomous fix lane on the PR branch, mirroring `/address-feedback`:

```bash
[[ "$PWD" == */.claude/worktrees/* ]] && IN_LANE=1 || IN_LANE=0
# cockpit: write plan to ~/.claude/plans/PR-<PR_NUM>-ci-fix.md (cause + fix slices,
# branch = headRefName, worktree = pr-<PR_NUM>-ci-fix), then:
wt --branch <headRefName> PR-<PR_NUM>-ci-fix
tmux rename-window "cifix:PR-<PR_NUM>"
```

`wt`'s pre-spawn `git fetch` + `--branch <headRefName>` checks out the real PR branch (reusing an existing lane if one already holds it) so fixes land as follow-up commits. Plan present → `wt` auto-starts the loop. Then stop: "Fix lane spawned on #<PR_NUM>'s branch. This pane is done."

- **Infra/flake/main-already-red** → no fix lane. Report the finding and the owner (CI config, base branch, retry).

## Stop conditions

- `gh` not authed / PR not found → report, stop.
- Can't reproduce locally AND logs are inconclusive → report what you tried + the artifact you'd need (full run log, secret, runner access). Never guess a fix without a repro.
