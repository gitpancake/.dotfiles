---
description: Personal Claude Code usage audit. Inventories config, parses the last 7 days of sessions, clusters repeated prompts, surfaces command/skill/workflow candidates. Output is one Markdown report at ~/.claude/audits/<name>-<YYYY-MM-DD>.md. Stage 1 of the team workflow-optimization plan — produces data, does not synthesize.
argument-hint: <name>
---

# /self-audit $ARGUMENTS

Produces an Audit Pack (Part A — auto-collected data) for the user identified by `$ARGUMENTS`. Feeds Stage 2 synthesis: command candidates, skill candidates, workflow candidates, config-hygiene work.

If `$ARGUMENTS` is empty, default to `$USER`.

**This command only reports.** Never edits commands, CLAUDE.md, or worktrees as a side effect — even if encyclopedia drift or stale worktrees are found.

## Output

One file: `~/.claude/audits/<name>-$(date +%Y-%m-%d).md`. Overwrite today's if it exists. Schema in §5 is the contract; everything else feeds it.

## 1. Inventory (discover, don't assume)

Probe `~/.claude/` for the actual layout — paths drift across Claude Code versions. Expected locations:

- Slash commands: `~/.claude/commands/*.md` + every `.claude/commands/*.md` under `~/Documents/code/`
- Skills: `~/.claude/skills/*/SKILL.md`
- Subagents: `~/.claude/agents/*.md`
- CLAUDE.md: `~/.claude/CLAUDE.md` + every `~/Documents/code/*/CLAUDE.md`

For each item: name, line count, byte count. Flag:

- Slash commands > 200 lines → encyclopedia smell (principle: pointer, not encyclopedia)
- Slash commands at **0 lines** → empty stub (Linear-era residue or unfinished). Surface as a distinct callout.
- CLAUDE.md > 150 lines → exceeds the global lean-config target

## 2. Worktree state

For each repo under `~/Documents/code/`:

```bash
git -C <repo> worktree list --porcelain
```

Per worktree: path, branch, age (`git -C <wt> log -1 --format=%ct HEAD`), PR status via `gh pr list --head <branch> --json number,state,url` if `gh` is installed, plus the repo's default branch (`git symbolic-ref refs/remotes/origin/HEAD` → fallback `gh repo view` → fallback local `main`/`master`).

**Stale = no commits in 5+ days AND no open PR AND branch is not the repo's default.** Bare entries excluded.

When rendering, separate **real stale feature lanes** from **dormant repo-main checkouts** — the latter aren't lanes to clean up.

## 3. Session shape, last 7 days

Claude Code stores transcripts as JSONL under `~/.claude/projects/<encoded-cwd>/<session-id>.jsonl`. **Don't assume the schema** — read one file first, infer the message shape, then parse.

For each session with `mtime >= now - 7d`:

- **Turn count** — user messages excluding tool results.
- **Turn-cap obedience** — search the stream for the turn-cap-warn.sh warning strings (`Turn 30 reminder`, `Turn 50`, `Turn 75 PAUSE`, `Turn 100+`). For each warning fired, did the user `/handoff` + `/clear` within 5 turns? Obedience ratio = honored / fired.
- **Slash command invocations** — regex user messages for `^/[a-z][a-z0-9-]*` and `<command-name>/foo</command-name>` form. Tally.
- **Tool calls** — count tool-use blocks per tool name in assistant messages.
- **Token usage** — sum `usage` blocks if present.

Aggregate:

- Session count, turn-count distribution (p50 / p75 / p95 / max)
- `/handoff` and `/clear` raw counts → flag if `clear`-dominant (state being dumped without state capture)
- Turn-cap warnings fired, obedience ratio
- Top-10 slash-command leaderboard
- Top-10 tool-call leaderboard
- Token usage totals (input / output / cache_read / cache_create)

**Cost discipline.** Parsing N session files via tool-call loop will burn context. Write a script once, reuse it.

- Script lives at `~/.claude/scripts/self-audit.ts` (bun). It does §1, §2, §3 and writes JSON to `~/.claude/audits/self-audit-<name>-<ISO-stamp>.json`. A `self-audit-<name>-latest.json` symlink points at the most recent run.
- Each invocation: `bun ~/.claude/scripts/self-audit.ts <name>` → read the JSON (path is on stdout, or use the `-latest.json` symlink) → render markdown.
- If the script exists but the JSONL schema has drifted (parse error rate spikes), regenerate it.

The script also emits two pre-computed Stage 2 flags directly in `sessionAgg.flags`:

- **`adoptionGaps`** — for each frequent prompt-theme (token-frequency, ≥2 events), fuzzy-match (Levenshtein ≥ 0.6, substring boost) to a slash/project command by name and emit `themeCount − invocations` where positive. Heads-up: autonomous `wt --ralph` lane spawn prompts dominate the histogram; treat very-high-count themes that look like lane spawn text as noise, not user intent. The Haiku clustering in §4 is the authoritative theme source — `adoptionGaps` is a cheap fallback when Haiku is unavailable.
- **`handoffVsClear`** — `{handoff, clear, handoffShare, flagged, note}`. `flagged: true` when ≥3 hygiene events and `handoffShare < 0.5`.

## 4. Bash command history (last 7 days)

Zsh extended history at `~/.zsh_history` carries epoch-prefixed entries:

```
: <epoch>:<duration>;<command>
```

Filter to `epoch >= now - 7d`. Multi-line commands span entries (continuation lines lack the `:` prefix) — join them before tallying.

Aggregate:

- **Total commands** + per-day distribution.
- **Top 20 by cmd+subcommand** — first two tokens (`git status`, `bun run`, `gh pr list`). This is the workflow-pattern view.
- **Top 10 verbatim commands** — exact repetition. A command appearing ≥10× verbatim is a wrapper-script candidate.
- **Long one-liners** — any command > 200 chars (after joining continuations). List the top 5. Alias / script candidate.
- **`&&`-chained recipes** — commands containing `&&` or `;` joiners with ≥3 segments. Top 5 by frequency. Strong workflow-script signal.

**Cost discipline.** Done by the §3 script — extend `self-audit.ts` to emit `bashHistory` into the same JSON. Inline parse is fine if the script is unavailable.

**Flag:**
- Cmd+subcommand ≥ 50 invocations → wrapper-script candidate.
- Verbatim command ≥ 10 invocations → alias candidate.
- `&&` chain ≥ 5 invocations → workflow-script candidate.

## 5. Filesystem layout (~/.claude/ + per-worktree `.claude/`)

The filesystem is the database (per `~/.claude/CLAUDE.md`). Sprawl = friction. Probe:

**Global `~/.claude/`:**

- `tickets/` — count per area, oldest brief mtime, total count. Flag areas with ≥ 20 briefs (re-org candidate). Flag briefs older than 30d (likely abandoned).
- `handoffs/` — count, oldest mtime. Flag if count > 50 (cleanup candidate) or any handoff > 30d (archive candidate).
- `plans/` — count, oldest mtime. Cross-reference each `<slug>.md` against active git branches (`git -C <wt> branch --show-current` across worktrees from §2). Plans with no matching branch = **orphan**. List orphans.
- `audits/` — count + dates.
- `scripts/` — file count, total line count, list any single file > 500 lines (refactor candidate).
- `projects/` (transcripts) — total size in GB. Flag if > 5GB (rotation candidate).

**Per-worktree `.claude/`** (from §2 worktree list):

- Presence: `.claude/agent-state`, `.claude/precheck.sh`, `.claude/verify.ok` per lane.
- Oversized: any file > 100KB inside a lane's `.claude/` (likely log accumulation — surface path + size).
- Stale state files: `agent-state` mtime > 7d while lane itself has 0d activity → state machine wedged.

**Flag:**
- Orphan plans → delete candidates.
- Handoffs > 30d → archive candidate.
- Tickets > 30d in non-epic areas → /scope decay.
- `projects/` > 5GB → transcript rotation.
- Wedged lane state → manual reset.

**Cost discipline.** Extend `self-audit.ts` to emit `filesystem` into the same JSON. Pure `stat` + `find` — no LLM.

## 6. Prompt clustering (one Haiku call)

§3 is deterministic; clustering is not.

Extract every **task opener** — the first user message of each session, plus any user message that starts a new chunk after `/clear`. Truncate each to 200 chars. Deduplicate exact matches. (The script already collects these into `openers[]`.)

Dispatch one subagent with `model: "haiku"`:

> Cluster these Claude Code task openers by semantic theme. Return JSON: `[{ "theme": "...", "count": N, "examples": ["...", "..."] }]`. Themes with count ≥ 3 are signal; below that, group into "other". Aim for 5–15 themes. The themes will be reviewed as candidates for new slash commands or skills.

Use the returned themes verbatim in §5. Do not re-cluster in the main session.

## 7. Output schema

Write to `~/.claude/audits/<name>-<YYYY-MM-DD>.md`:

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
- /handoff: N      /clear: N
- Turn-cap warnings fired: N
- Turn-cap obedience: X% (honored within 5 turns of warning)
- Token usage: input · output · cache-read · cache-create

### Slash command leaderboard
| Command | Invocations |

### Tool-call leaderboard
| Tool | Calls |

## Bash history (last 7 days)
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
- /handoff vs /clear split → if `flagged: true`, surface as session-hygiene candidate (auto-handoff hook)
- Turn-cap obedience < 50% → session-hygiene candidate (auto-handoff hook)
- Stale worktrees > 3 → cleanup-automation candidate
- Top tool calls dominated by Bash → possible workflow-script candidate
- Bash cmd+subcommand ≥ 50 invocations → wrapper-script candidate
- Verbatim bash command ≥ 10 invocations → alias candidate
- `&&` chain ≥ 5 invocations → workflow-script candidate
- Orphan plans → delete candidates
- Handoffs > 30d → archive candidate
- Tickets > 30d outside epics → /scope decay
- ~/.claude/projects/ > 5GB → transcript rotation
- Wedged lane state → manual reset
```

Stage 2 (synthesis — what to *do* with this) is out of scope for this command. Produce the data, stop.

## 8. On completion

Print the output path. Print a one-line summary of the top four flags (encyclopedia commands count, obedience ratio, stale worktree count, top repeated bash command). Stop.

## Stop conditions

- `~/.claude/projects/` missing or empty → report, write inventory + worktree sections only, mark session block `unavailable`.
- Script in §3 fails → report the error, do not fabricate session stats. Inventory + worktree still written.
- `~/.zsh_history` missing or unreadable → skip §4, mark `unavailable`. Do not fail the audit.
- Haiku clustering fails → write the deduped opener list as a raw `<details>` block under "Repeated prompt themes" for manual clustering. Do not fail the whole audit.

Never edit code. Never create Linear tickets. Never modify slash commands or CLAUDE.md.
