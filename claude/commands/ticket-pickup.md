---
description: Scope a Linear ticket into a merge-safe slice plan, then spawn an autonomous worktree lane.
argument-hint: <LINEAR-ID> [base-branch] [--type feature|fix|chore|task|refactor]
---

# /ticket-pickup $ARGUMENTS

Produce a scoping doc at `~/.claude/plans/<TICKET>.md`, then spawn an autonomous worktree lane (§11). Do **not** edit any project source file.

## Argument parsing

`$ARGUMENTS` = `<TICKET> [base-branch] [--type <prefix>]`. First positional token = Linear ticket ID (required). Second positional = base branch (optional; defaults to cockpit's current branch). `--type` (optional) = branch type prefix override; empty → auto-detect from labels (§1.5). Empty ticket → ask and stop.

## 1. State check (parallel)

- `mcp__linear-server__get_issue <TICKET>` → body, comments, status, priority, assignee, labels, parent, sub-issues, **attachments**.
- If `BASE` was passed: `git rev-parse --verify "origin/<BASE>"` — stop if missing.

Linear `attachments[]` already names linked PRs. Fall back to `gh pr list --search "<TICKET>" --state all` and `git log --all --grep="<TICKET>"` only if attachments are empty.

**Linked tickets**: fetch parent + tickets named in `relations.blocks`/`blockedBy` only. Defer sibling/related fetches until a slice needs them. Plan-lint flags fetched-but-never-referenced tickets as `over-fetched` notes — keep §1 fetches lean.

**Stop conditions** (report and wait): in-progress + assignee not user; open PR exists; `Blocked` label or unresolved blocker comment.

## 1.5. Type detection

If `--type` was passed, use it. Otherwise infer from Linear labels:

| Label contains | Type | Branch prefix |
|---|---|---|
| `bug` | fix | `fix/` |
| `refactor` | refactor | `refactor/` |
| `chore`, `infra`, `ops` | chore | `chore/` |
| none of the above | feature | `feature/` |

First match wins. Record `TYPE` for use in §3 and §5. Print detected type so user can override before planning starts.

## 2. Verbatim extraction

Copy directly, do not paraphrase:

- **Acceptance criteria** — copy from ticket. None? Say so, propose criteria for confirmation.
- **Out of scope** — copy from ticket. Absent? List your *assumptions* so user can correct.
- **Linked tickets** — one line each: `ID — title — status`.
- **Recent comments** — last 5 verbatim if they shift scope/constraints.

## 2.5. Bug investigation (TYPE=fix only)

Skip for feature/refactor/chore. Goal: establish root cause before planning. Do not propose a fix yet.

### Evidence gathering (parallel)

Run all available sources in parallel. Not every source will exist in every project — skip gracefully.

- **Sentry**: search for recent errors matching ticket description, affected file paths, or error messages quoted in ticket/comments. Note: requires Sentry access — if unavailable, flag and move on.
- **tracing-tool traces**: search for failing/erroring traces in the affected workflow area. Look for: low scores, error status, unexpected tool calls, hallucinated outputs. Link specific trace IDs.
- **Git blame + recent commits**: `git log --since="2 weeks ago" -- <affected files>` and `git blame <affected files>` on the lines mentioned in the ticket. Look for recent regressions — the bug may be a side effect of a recent change.
- **Log search**: grep application logs (Loki, CloudWatch, local) for error patterns, stack traces, or the specific error message from the ticket.

### Root cause summary

After gathering evidence, write a **root cause hypothesis** (2-3 sentences max):
- What's broken and where (file:line if known).
- When it started (commit hash or date range if identifiable from blame/logs).
- Why it breaks (the mechanism, not just the symptom).

If root cause is unclear after investigation, flag it in §6 (Open questions) as a blocker — don't guess.

## 3. Mirror search (TYPE=feature only)

Skip for fix/refactor/chore. Most example-org-agent work is "mirror the X equivalent for Y" shaped. Name the analogous feature first; list its entry points (workflow, route, model, UI). For vendor integrations, search OpenViking `resources/example-org/<vendor>/` first; cite `source_file § section` for any spec claim.

## 4. Surface area (grounded grep, only after §2.5/§3)

Top ≤10 files to read first, each with a one-line reason. Imports/callers of affected types. Quote any project `CLAUDE.md` "Gotchas" entries that apply.

## 5. Slice plan (trunk-based, merge-safe)

Each slice ships to main on its own. Plan structure adapts to `TYPE`:

### TYPE=feature (default)

Standard multi-slice with flip pattern. User sees nothing until final flip.

| # | Slice | User-visible? | Why safe to merge alone |
|---|-------|---------------|-------------------------|
| 1 | … | No | … |
| N | **Flip** | Yes | One-line registry/endpoint change |

### TYPE=fix

Typically 1-2 slices. Root cause from §2.5 drives the plan. No flip needed — the fix IS the user-visible change.

| # | Slice | What |
|---|-------|------|
| 1 | Fix + regression test | Targeted fix at root cause. Test reproduces the bug, then verifies the fix. |
| 2 | *(optional)* Hardening | Guard clause, validation, or monitoring to prevent recurrence. |

If the fix touches multiple layers (schema + backend + frontend), still split by layer but each slice targets the same root cause.

### TYPE=refactor

No user-visible change. Require test coverage audit before touching code — if existing tests are insufficient, slice 1 adds them.

| # | Slice | What |
|---|-------|------|
| 1 | *(if needed)* Test backfill | Add/expand tests covering the code about to change. |
| 2+ | Refactor chunks | Each chunk passes existing + new tests. |

### TYPE=chore

Lightweight. Often single-slice. Skip DAG. Config, deps, infra — no user-facing flip.

### General rules (all types)

If a slice can't merge alone without breaking main or showing half-finished UI, restructure until it can.

### 5b. DAG block

If slice count > 1, embed a `<!-- slice-dag:start -->` … `<!-- slice-dag:end -->` block per `~/.claude/dag-schema.md`. Used by `wt --dag <TICKET>` to spawn ready slices in parallel. Single-slice plans may omit.

## 6. Open questions — split

**Ambiguous** — concrete question + who to ask (ticket author / Alex / Sam / #eng-chat / customer).
**Risky** — what breaks if wrong + rollback path.

## 7. Estimate

Slice count (1/3/5/8). Comparable prior plan from `~/.claude/plans/` ("M like AE-XXXX"). Top 1–2 unknowns that would shift it up.

## 8. ExampleCorp-specific checks (if working in example-org-agent)

- Prompts/context/system messages → llm-vendor cache-prefix risk (95% bar).
- Error handling/Sentry/catch → no catch-and-swallow; threshold-0 norm.
- Function signatures with multiple primitives → object-params rule.
- Tests → `bun test` (`:vm` flag required in worktrees).
- Trigger.dev tasks → both `TaskRegistry` and `TASK_ROUTES_ENV` updated.

## 9. Branch + worktree (planning only)

Branch: `<TYPE>/<ticket-id-lower>-<descriptor>` where `<TYPE>` is from §1.5. `<descriptor>` is the slugified ticket title (lowercased, non-alnum → `-`, trimmed, ≤50 chars). Worktree: `<repo>/.claude/worktrees/<ticket-id-lower>-<descriptor>`. Base: `BASE` if passed, else cockpit's current branch. Record branch, worktree, and base in plan.

## 10. Linear comment

Post via `mcp__linear-server__save_comment`:

> Scoping in progress for <TICKET>. Plan at `~/.claude/plans/<TICKET>.md`. Reviewing with @henry before any code edits.

## 10.5 Plan-lint gate

Run `~/.claude/scripts/plan-lint.sh <TICKET>`.

- If output starts with `plan-lint: CACHED` → skip the subagent. Read `~/.claude/plans/<TICKET>.lint.md` directly.
- Otherwise → dispatch the `plan-lint` subagent with `TICKET`, `PLAN_PATH`, `VERDICT_PATH`. Then read the verdict file.

Force re-lint with `PLAN_LINT_FORCE=1 ~/.claude/scripts/plan-lint.sh <TICKET>` if the plan didn't change but the upstream Linear ticket did.

- **PASS** → §11.
- **FAIL** → STOP. Print gap table to user. Do not spawn a lane. user can `/rescope` or hand-edit, then re-run.

## 11. Spawn the lane

Detect lane:

```bash
[[ "$PWD" == */.claude/worktrees/* ]] && IN_LANE=1 || IN_LANE=0
```

### Cockpit (`IN_LANE=0`)

If `BASE` was passed, sync cockpit first (`wt` only ff-merges main/master):

```bash
[ -n "$BASE" ] && git fetch --quiet origin && git checkout "$BASE" && git merge --ff-only "origin/$BASE"
```

Then spawn the autonomous lane. **You MUST run this command via the Bash tool** — it opens a new tmux window with claude in autonomous mode:

```bash
wt --type <TYPE_PREFIX> <TICKET>
```

Where `<TYPE_PREFIX>` is the `TYPE` from §1.5 and `<TICKET>` is the uppercase Linear ID (e.g. `TEAM-1609`). `wt` creates the worktree + branch, allocates a per-lane port, and opens a new tmux window running claude with the plan. Stop after spawning:

> Lane spawned. Autonomous dev loop running in new tmux window. This pane is done.

### Inside a lane (`IN_LANE=1`)

`/ticket-pickup` was invoked from inside an autonomous lane (don't recurse). Continue inline:

> Plan ready. Beginning autonomous implementation. Slices commit per layer; no inter-slice confirmation. /ship at end.

Proceed straight to slice 1. Stop only on /ship complete + PR up, or genuine blocker (ambiguity, repeated failure, missing credential). Never stop "to confirm before slice N."
