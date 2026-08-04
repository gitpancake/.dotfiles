# /retrospective draft template — the contract

Structure for the §4 draft. Bullets concrete and evidence-backed — cite PR numbers, commit
hashes, or ticket IDs inline. No filler. The doc trains a planning agent; write it like an
engineer, not a manager. Only write what the data actually supports.

---

**By the Numbers**

| Metric | Value |
|--------|-------|
| PRs total / merged / abandoned / abandon rate | |
| Mega PRs | |
| Architectural pivots | |
| Rework clusters | |
| Calendar days | |

**Timeline**

For each phase (from §3b): phase name + date range, PR count, dominant theme, key decisions
(what changed direction or got locked in), pivots in this phase.

**What Went Well**

A few bullets, each citing evidence (PR #, ticket ID, or commit). No unsubstantiated claims.

**What Went Wrong**

For each item: what happened → why it hurt → what it cost (wasted PRs, delay,
re-architecture). Categories to check: §3c pivots, §3e mega PRs, missing discovery (things
only found during implementation), late testing/integration, high-abandon-rate phases.

**Lessons for Future Work**

Two callout blocks — only lessons the data supports:

> **Planning Phase**
> - <lesson>: <what to do differently>

> **Execution Phase**
> - <lesson>: <what to do differently>

**Abandoned PR Log**

Collapsible list (Notion toggle) of all closed-not-merged PRs: number, title, date closed,
additions+deletions, reason (inferred from title / surrounding commits / replacement PR —
flag as "inferred" if not explicit).
