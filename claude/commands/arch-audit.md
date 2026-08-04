---
description: Architecture audit — smells/DRY/SOLID/complexity sweep → ranked findings → Linear ticket proposals. Report-only until "go".
argument-hint: [path]
---

# /arch-audit $ARGUMENTS

Audits the repo's code architecture and proposes tickets. Two mirrors govern this
command: `/self-audit` (report-only posture, stop conditions) and `/scope` §4–6
(ticket house style, draft-stop-go cadence). **Never edits code. Never creates
branches, worktrees, or Linear anything.**

If `$ARGUMENTS` names a path, audit only that subtree. Empty → whole repo.

## 1. Scope discovery

- `git rev-parse --show-toplevel` → repo root + basename. Not a git repo → audit
  cwd and say so in the report header.
- Discover modules: prefer `apps/*` + `packages/*` (monorepo), else `src/<domain>/`,
  else treat the root as one module. Skip generated/vendor dirs (`node_modules`,
  `.next`, `dist`, `build`) and lockfiles.
- Read the project's `CLAUDE.md` / `AGENTS.md` / `CONTEXT.md` first — conventions
  there are law. A "smell" the project explicitly mandates is not a finding.

## 2. Fan-out — per-module agents + one cross-cutting agent

**Cap: 6 agents total** (≤5 module agents + 1 cross-cutting). More modules than
slots → merge the smallest modules (by line count) into one agent's scope.

Spawn read-only **Explore** agents in parallel, one per module. Audit dimensions:
code smells (cite canonical refactoring.guru catalog names), DRY, over-complication,
dead code, SOLID/dependency direction, composition-over-inheritance, pattern fit.
A pattern must pay for itself — "could use a pattern" alone is not a finding.

Each finding returns as: `file:line` evidence · smell name · suggested refactoring
(canonical refactoring.guru name) · one-line payoff · S/M/L effort.

The **cross-cutting agent** hunts only cross-module concerns: duplication *between*
packages, dependency direction / layering violations, shared-abstraction
candidates, inconsistent idioms for the same job.

Inline shared facts (repo root, module list, convention summary) into every agent
prompt — siblings never re-derive.

## 3. Synthesis + rubric

Merge in the main session, dedupe (same file + same theme = one finding), rank by
**payoff ÷ effort**.

- Keep the ticket set small enough to actually get picked up — quality bar over
  quantity; when in doubt a finding goes to the noted list, not a brief.
- ≥3 findings sharing one structural theme → propose an **epic** (Linear project +
  child issues, blocking relations as the DAG); isolated findings → single issues.
- Everything below the bar → **"noted, not ticketed"** list. Never written as tickets.

## 4. Draft. Stop.

Render in chat:

1. Findings table — rank, file:line, smell, refactoring, payoff, size.
2. Proposed ticket set — titles, teams, epic-vs-singles grouping.
3. The noted-not-ticketed list.

**Stop.** Write nothing before an explicit "go". Edits → revise, re-render, stop
again.

## 5. On "go": write

- Tickets → Linear via the `linear` skill, house style per `/scope` §4 (description
  sections, team per global CLAUDE.md §Linear teams, blocking relations for epics).
  - Each description: Context quotes the finding's evidence; acceptance criteria state
    the verifiable refactoring outcome, never "improve code".
- Full audit (including noted-not-ticketed) →
  `~/.claude/audits/arch-<repo-basename>-<YYYY-MM-DD>.md`, overwriting same-day
  output.
- Return ticket paths + a `wt <slug>` hint.

## Stop conditions

- After §4 draft — wait for "go".
- Zero above-bar findings → report "clean at this bar" plus the noted list; write
  the audit report only if asked. Done.
- A subagent fails → synthesize from the rest, mark that module `unavailable` in
  the draft. Never fabricate findings.
