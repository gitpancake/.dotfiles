---
description: Scope a Linear ticket into a merge-safe slice plan. Stops before implementation.
argument-hint: <LINEAR-ID> [base-branch] [--type feature|fix|chore|task|refactor]
---

# /ticket-pickup $ARGUMENTS

Produce a scoping doc at `~/.claude/plans/<TICKET>.md`. Do **not** edit any other file. Stop after writing the plan and posting the Linear comment.

## Argument parsing

`$ARGUMENTS` = `<TICKET> [base-branch] [--type <prefix>]`. First positional token = Linear ticket ID (required). Second positional = base branch (optional; defaults to cockpit's current branch). `--type` (optional) = branch type prefix passed through to `wt`; default `feature`. Empty ticket → ask and stop.

## 1. State check (parallel)

- `mcp__linear-server__get_issue <TICKET>` → body, comments, status, priority, assignee, labels, parent, sub-issues, **attachments**.
- If `BASE` was passed: `git rev-parse --verify "origin/<BASE>"` — stop if missing.

Linear `attachments[]` already names linked PRs. Fall back to `gh pr list --search "<TICKET>" --state all` and `git log --all --grep="<TICKET>"` only if attachments are empty.

**Linked tickets**: fetch parent + tickets named in `relations.blocks`/`blockedBy` only. Defer sibling/related fetches until a slice needs them. Plan-lint flags fetched-but-never-referenced tickets as `over-fetched` notes — keep §1 fetches lean.

**Stop conditions** (report and wait): in-progress + assignee not user; open PR exists; `Blocked` label or unresolved blocker comment.

## 2. Verbatim extraction

Copy directly, do not paraphrase:

- **Acceptance criteria** — copy from ticket. None? Say so, propose criteria for confirmation.
- **Out of scope** — copy from ticket. Absent? List your *assumptions* so user can correct.
- **Linked tickets** — one line each: `ID — title — status`.
- **Recent comments** — last 5 verbatim if they shift scope/constraints.

## 3. Mirror search (before grep)

Most example-org-agent work is "mirror the X equivalent for Y" shaped. Name the analogous feature first; list its entry points (workflow, route, model, UI). For vendor integrations, search OpenViking `resources/example-org/<vendor>/` first; cite `source_file § section` for any spec claim.

## 4. Surface area (grounded grep, only after §3)

Top ≤10 files to read first, each with a one-line reason. Imports/callers of affected types. Quote any project `CLAUDE.md` "Gotchas" entries that apply.

## 5. Slice plan (trunk-based, merge-safe)

Each slice ships to main on its own. User sees nothing until the final flip.

### 5a. Human table

| # | Slice | User-visible? | Why safe to merge alone |
|---|-------|---------------|-------------------------|
| 1 | … | No | … |
| N | **Flip** | Yes | One-line registry/endpoint change |

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

Branch: `<type>/<ticket-id-lower>-<descriptor>` where `<type>` defaults to `feature` (override via `--type`). `<descriptor>` is the slugified ticket title (lowercased, non-alnum → `-`, trimmed, ≤50 chars). Worktree: `<repo>/.claude/worktrees/<ticket-id-lower>-<descriptor>`. Base: `BASE` if passed, else cockpit's current branch. Record branch, worktree, and base in plan.

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

Then `wt [--type <prefix>] <TICKET>`. `wt` creates the worktree + branch (`<type>/<ticket>-<descriptor>`), allocates a per-lane port, opens a new claude lane with autonomous-mode kickoff. Pass `--type` through if user specified one. Stop after spawning:

> Lane spawned. Autonomous dev loop running there. This pane is done.

### Inside a lane (`IN_LANE=1`)

`/ticket-pickup` was invoked from inside an autonomous lane (don't recurse). Continue inline:

> Plan ready. Beginning autonomous implementation. Slices commit per layer; no inter-slice confirmation. /ship at end.

Proceed straight to slice 1. Stop only on /ship complete + PR up, or genuine blocker (ambiguity, repeated failure, missing credential). Never stop "to confirm before slice N."
