---
description: Claude Code usage audit — config + 7d sessions → workflow/command/skill candidates. → md report at ~/.claude/audits/.
argument-hint: <name>
---

# /self-audit $ARGUMENTS

Produces an Audit Pack (Part A — auto-collected data) for the user identified by `$ARGUMENTS`. Feeds Stage 2 synthesis: command candidates, skill candidates, workflow candidates, config-hygiene work.

If `$ARGUMENTS` is empty, default to `$USER`.

**This command only reports.** Never edits commands, CLAUDE.md, or worktrees as a side effect — even if encyclopedia drift or stale worktrees are found.

## Output

One file: `~/.claude/audits/<name>-$(date +%Y-%m-%d).md`. Overwrite today's if it exists. Render per the schema at `~/.claude/docs/self-audit-schema.md` — that file is the contract; everything below feeds it.

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
- **Slash command invocations** — regex user messages for `^/[a-z][a-z0-9-]*` and `<command-name>/foo</command-name>` form. Tally.
- **Tool calls** — count tool-use blocks per tool name in assistant messages.
- **Token usage** — sum `usage` blocks if present.

Aggregate:

- Session count, turn-count distribution (p50 / p75 / p95 / max)
- `/handoff` and `/clear` raw counts → flag if `clear`-dominant (state being dumped without state capture)
- Top-10 slash-command leaderboard
- Top-10 tool-call leaderboard
- Token usage totals (input / output / cache_read / cache_create)

**Cost discipline.** Parsing N session files via tool-call loop will burn context. Write a script once, reuse it.

- Script lives at `~/.claude/scripts/self-audit.ts` (bun). It does §1, §2, §3 and writes JSON to `~/.claude/audits/self-audit-<name>-<ISO-stamp>.json`. A `self-audit-<name>-latest.json` symlink points at the most recent run.
- Each invocation: `bun ~/.claude/scripts/self-audit.ts <name>` → read the JSON (path is on stdout, or use the `-latest.json` symlink) → render markdown.
- If the script exists but the JSONL schema has drifted (parse error rate spikes), regenerate it.

The script also emits two pre-computed Stage 2 flags directly in `sessionAgg.flags`:

- **`adoptionGaps`** — for each frequent prompt-theme (token-frequency, ≥2 events), fuzzy-match (Levenshtein ≥ 0.6, substring boost) to a slash/project command by name and emit `themeCount − invocations` where positive. Heads-up: autonomous `wt` lane spawn prompts dominate the histogram; treat very-high-count themes that look like lane spawn text as noise, not user intent. The Haiku clustering in §4 is the authoritative theme source — `adoptionGaps` is a cheap fallback when Haiku is unavailable.
- **`handoffVsClear`** — `{handoff, clear, handoffShare, flagged, note}`. `flagged: true` when ≥3 hygiene events and `handoffShare < 0.5`.

## 4. Shell command history (last 7 days)

Detect the user's shell history file in order:

1. **Zsh extended** — `~/.zsh_history`. Format: `: <epoch>:<duration>;<command>`. Multi-line commands continue on subsequent lines without the `:` prefix — join before tallying.
2. **Bash w/ timestamps** — `~/.bash_history` *and* `$HISTTIMEFORMAT` set (heuristic: file contains lines starting with `#<10-digit-epoch>`). Format: alternating `#<epoch>` / `<command>` blocks.
3. **Bash plain** — `~/.bash_history` with no timestamp lines. **Cannot 7d-filter** — read the whole file and mark the section `window: all-time (no timestamps in bash history)`.
4. **None found** → mark `unavailable`, skip §4.

If both zsh and bash histories exist, prefer whichever was modified more recently (matches the active shell).

Filter (where possible) to `epoch >= now - 7d`.

Aggregate:

- **Total commands** + per-day distribution.
- **Top 20 by cmd+subcommand** — first two tokens (`git status`, `bun run`, `gh pr list`). This is the workflow-pattern view.
- **Top 10 verbatim commands** — exact repetition. A command appearing ≥10× verbatim is a wrapper-script candidate.
- **Long one-liners** — any command > 200 chars (after joining continuations). List the top 5. Alias / script candidate.
- **`&&`-chained recipes** — commands containing `&&` or `;` joiners with ≥3 segments. Top 5 by frequency. Strong workflow-script signal.

**Cost discipline.** Done by the §3 script — extend `self-audit.ts` to emit `shellHistory` into the same JSON, carrying the detected shell + window (7d or all-time) alongside the aggregates. Inline parse is fine if the script is unavailable.

**Flag:**
- Cmd+subcommand ≥ 50 invocations → wrapper-script candidate.
- Verbatim command ≥ 10 invocations → alias candidate.
- `&&` chain ≥ 5 invocations → workflow-script candidate.

## 5. Filesystem layout (~/.claude/ + per-worktree `.claude/`)

The filesystem is the database (per `~/.claude/CLAUDE.md`). Sprawl = friction. Probe:

**Global `~/.claude/`:**

- `tickets/` — materialization cache only (Linear is the tracker). Flag cache files older than 30d (stale — safe to delete; `linear-brief.sh` re-materializes on demand).
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

Use the returned themes verbatim in the "Repeated prompt themes" section of the output. Do not re-cluster in the main session.

## 7. Render

Render the JSON to `~/.claude/audits/<name>-<YYYY-MM-DD>.md` per `~/.claude/docs/self-audit-schema.md` — section names, table shapes, and the Stage 2 flag list all come from that file.

Stage 2 (synthesis — what to *do* with this) is out of scope for this command. Produce the data, stop.

## 8. On completion

Print the output path. Print a one-line summary of the top four flags (encyclopedia commands count, handoff share, stale worktree count, top repeated shell command). Stop.

## Stop conditions

- `~/.claude/projects/` missing or empty → report, write inventory + worktree sections only, mark session block `unavailable`.
- Script in §3 fails → report the error, do not fabricate session stats. Inventory + worktree still written.
- No shell history found (zsh + bash both missing/unreadable) → skip §4, mark `unavailable`. Do not fail the audit.
- Haiku clustering fails → write the deduped opener list as a raw `<details>` block under "Repeated prompt themes" for manual clustering. Do not fail the whole audit.

Never edit code. Never create Linear tickets. Never modify slash commands or CLAUDE.md.
