# /self-audit output schema — the contract

Rendered to `~/.claude/audits/<name>-<YYYY-MM-DD>.md` from the JSON emitted by
`~/.claude/scripts/self-audit.ts`. Section names and table shapes are the contract;
`/self-audit` §1–§6 feed it.

```
# Audit Pack — <name> — <date>

Part A — auto-collected data. Feeds Stage 2 synthesis. This document reports only; no config was edited.

## Inventory

### Slash commands (<count>)
| Name | Lines | Flag |
|------|-------|------|
(⚠ if > 200, empty stub if 0)

### Skills (<count>)
(same shape)

### Subagents (<count>)
(same shape)

### CLAUDE.md files
| File | Lines | Flag |
|------|-------|------|
(⚠ if > 150)

## Worktrees — <active> active, <stale> stale
| Path | Branch | Age | PR | Stale? |
|------|--------|-----|-----|--------|

Note: separate real stale feature lanes from dormant repo-main checkouts.

## Sessions (last 7 days)
- Total sessions: N
- Turn-count distribution: p50=X, p75=Y, p95=Z, max=W
- /handoff: N      /clear: N   (handoffShare, flagged if <0.5 on ≥3 events)
- Token usage: input · output · cache-read · cache-create

### Slash command leaderboard
| Command | Invocations |

### Tool-call leaderboard
| Tool | Calls |

## Shell history (<shell>, <window>)
- Total commands: N
- Top 20 cmd+subcommand
| Cmd | Invocations |
- Top 10 verbatim commands
| Command | Count |
- Long one-liners (>200 chars): top 5
- `&&`-chains (≥3 segments): top 5 by frequency

## Filesystem layout
### Global ~/.claude/
| Path | Count | Oldest | Flag |
|------|-------|--------|------|
(tickets per area, handoffs, plans, audits, scripts, projects size)

### Orphan plans (no matching branch)
- list

### Per-worktree .claude/
- Lanes missing agent-state / precheck.sh: list
- Oversized files (>100KB) inside lane .claude/: list path + size
- Wedged state (agent-state mtime > 7d on active lane): list

## Repeated prompt themes
| Theme | Count | Examples |
|-------|-------|----------|
(only themes with count ≥ 3; rest collapsed into "other")

## Stage 2 flags
- High-frequency themes (count ≥ 5) → command/skill candidates. Cross-reference each theme against the slash leaderboard — a theme with many openers but few matching command invocations is an adoption gap.
- Slash commands > 200 lines → refactor candidates (encyclopedia drift)
- Empty (0-line) slash command stubs → delete candidates
- CLAUDE.md > 150 lines → lean-config refactor candidates
- handoffShare < 0.5 → session-hygiene candidate
- Stale worktrees > 3 → cleanup-automation candidate
- Top tool calls dominated by Bash → possible workflow-script candidate
- Shell cmd+subcommand ≥ 50 invocations → wrapper-script candidate
- Verbatim shell command ≥ 10 invocations → alias candidate
- `&&` chain ≥ 5 invocations → workflow-script candidate
- Orphan plans → delete candidates
- Handoffs > 30d → archive candidate
- Tickets > 30d outside epics → /scope decay
- ~/.claude/projects/ > 5GB → transcript rotation
- Wedged lane state → manual reset
```
