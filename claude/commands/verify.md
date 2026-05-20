---
description: Exercise a PR's changes end-to-end via the verifier subagent — real UI/API/DB/worker runs, evidence written, PASS/FAIL verdict. Read-only; certifies, never fixes.
argument-hint: <PR number or URL — omit to use the current branch's PR>
---

# /verify $ARGUMENTS

Turn "what verification do we have that #N works" into evidence. Resolve the PR, get its changes onto a runnable checkout, hand off to the **`verifier` subagent** — which exercises the feature for real (UI in a browser, API via curl, DB via query, worker via enqueue) and writes `verify.log` + a `verify.ok` stamp on PASS. The verifier has no Edit tool: it certifies, it does not fix. A green type-check is not verification.

## 0. Resolve target

`$ARGUMENTS` = PR number or URL. Empty → current branch's PR: `gh pr view --json number,headRefName,baseRefName,state,title` (no arg = current branch). No PR → ask for a number and stop. Extract `PR_NUM`, `HEAD`, `BASE` (its `baseRefName`), `STATE`.

`MERGED`/`CLOSED` → note it; verify only if the user still wants the historical check.

## 1. Find a runnable checkout for HEAD

The verifier runs **real** commands — it needs the branch's installed deps and env, not just the source. Prefer an existing lane; fall back to a throwaway worktree.

1. **Already on it** — `git branch --show-current` == `HEAD` → `TARGET=$PWD`, `MODE=here`. Skip to §2.
2. **An existing lane holds it** — `git worktree list --porcelain | grep -A2 "branch refs/heads/$HEAD"` (a lane under `.claude/worktrees/`) → `TARGET=<that path>`, `MODE=lane`. It already has `node_modules` + `.env.local`. Skip to §2.
3. **Neither** — `MODE=throwaway`:
   ```
   git fetch origin "$HEAD" --prune
   TARGET=$(mktemp -d -t verify-${HEAD//\//-}-XXXX)
   git worktree add "$TARGET" -B "$HEAD" "origin/$HEAD"
   ```
   A fresh worktree has **no deps and no env**. Before dispatch:
   - `package.json` present → `bun install` in `$TARGET` (per project; lanes use bun).
   - No `.env.local` → warn: env-dependent classes (UI dev server, authed API, DB) will likely FAIL without it. Do not fabricate env. If the diff is a pure refactor / unit-testable change, proceed; otherwise tell the user a lane checkout verifies more faithfully and ask whether to continue.

## 2. Dispatch the verifier

Dispatch the **`verifier` subagent** (Agent tool, `subagent_type: "verifier"`) with its working directory at `$TARGET`. Pass:

- `BRANCH=$HEAD`
- `DIFF_BASE=origin/$BASE` — so it reads exactly this PR's diff (`git diff origin/$BASE...HEAD`), not the whole branch history.

The verifier classifies the diff (UI / API / DB / worker / pure-refactor), runs real verification per class, appends to `$TARGET/.claude/verify.log`, and on full PASS writes `$TARGET/.claude/verify.ok`. On FAIL it tags the lane (`lane-pause.sh verify`) and prints the failing evidence block. Do not summarize the diff for it — it reads the diff itself.

## 3. Report — terse

Relay the verifier's verdict; don't re-run its work:

```
verify #<PR_NUM> (<HEAD>): PASS|FAIL — <one-line summary>
mode:  here | lane (<path>) | throwaway (<path>)
log:   <TARGET>/.claude/verify.log
stamp: <TARGET>/.claude/verify.ok | (none — FAIL)
```

FAIL → also paste the verifier's last `===` evidence block so the cause is visible without opening the log.

## 4. Cleanup

- `MODE=here` / `MODE=lane` → leave it; the lane owns its state (`verify.ok` is a real signal there).
- `MODE=throwaway` → **PASS**: `git worktree remove "$TARGET" && git branch -D "$HEAD"`. **FAIL**: keep it, print the path so the user can inspect the failing run.

## 5. Stop

Report the verdict and stop. `/verify` does not fix failures or push — on FAIL, surface the evidence and let the user decide (fix lane via `/address-feedback` or `/why-failing`, or hand-fix). It is the gate, not the patch.
