# claude

Configuration, hooks, agents, commands, skills, and lane primitives for [Claude Code](https://claude.com/claude-code). Symlinked into `~/.claude/` by the installers.

## Files

| File | Purpose |
| --- | --- |
| `settings.json` | Claude Code settings: enabled plugins, statusline command, hooks, model, permission defaults. |
| `CLAUDE.md` | **Global instructions** loaded into every Claude session — workflow rules, code-quality, cost discipline, OpenViking protocol, agent routing, turn-cap protocol. |
| `statusline-command.sh` | Renders Claude Code's bottom status bar: context-window bar + 5h/7d rate-limit alerts, color-coded by severity. |
| `transcript-costs.sh` | Post-mortem tool: ranks recent sessions by cost so you can spot expensive transcripts. |
| `agent-state-vocab.md` | Reason-code vocab for lane `WAITING:<code>` states. |
| `worktree-protocol.md` | Multi-agent worktree safety rules. |

## Subdirectories

| Dir | What's in it |
| --- | --- |
| `agents/` | Specialist subagent profiles — `backend`, `frontend`, `database`, `fullstack`, `infra`, `bugfinder`, `plan-lint`, `verifier`. Dispatched via the `Agent` tool. |
| `commands/` | Slash commands available in every project (see catalog below). |
| `skills/` | Skills — `grill-with-docs`, `to-issues`, `tdd`, `diagnose`, `handoff`. Each is a dir with `SKILL.md`. |
| `hooks/` | Shell hooks invoked on session events (notification, tool use, stop, user-prompt-submit). |
| `scripts/` | Remaining helper scripts — `ticket-status-sync.py` (used by `TIX_PRELOAD_HOOK` and `WT_TICKET_SYNC`), `plan-lint.sh`, `verify-clean.sh`, `prune-*.sh`. Lane-orchestration scripts moved to **[wt-lanes](https://github.com/gitpancake/wt-lanes)**. |
| `bin/` | PATH-exposed leftover tools — `git-watch`, `slack-tldr`, `slack-watch`. Lane bins (`wt`, `wt-gc`, `ralph-bootstrap`) moved to **[wt-lanes](https://github.com/gitpancake/wt-lanes)**. `tix` ships from **[tix](https://github.com/gitpancake/tix)** (`pipx install tix-cli`). |

LaunchAgent plists (installed into `~/Library/LaunchAgents/`):

| Plist | Job |
| --- | --- |
| `local.claude-plan-prune.plist` | Daily prune of `~/.claude/plans/`. |
| `local.claude-transcript-prune.plist` | Weekly prune of `~/.claude/projects/*/`. |
| `local.claude-wt-gc.plist` | Periodic `wt-gc` to reap dead lanes. |
| `local.slack-tldr.plist` | Slack TLDR daemon (only loaded when `scripts/slack-tldr.config.local` exists). |

## Parallel worktree lanes

Lane orchestration (`wt`, `wt-gc`, `ralph-bootstrap`, `agent-board`, hooks, Ralph) now lives in **[wt-lanes](https://github.com/gitpancake/wt-lanes)**. Install with `git clone https://github.com/gitpancake/wt-lanes ~/.wt-lanes && ~/.wt-lanes/install.sh`. The rest of this section describes how this dotfiles repo uses it.

`wt <slug-or-epic>` spawns one parallel lane per ticket. Each lane is fire-and-forget: reads the local brief, works it through to a PR, then stops.

What `wt` produces:

- worktree at `<repo>/.claude/worktrees/<slug>`
- branch `<type>/<slug>` off current HEAD
- per-lane port stamped in `.env.local.port` (3099 + lane index)
- `.claude/agent-state` seeded to `IDLE` (visible to `tmux/agent-board.sh`)
- new tmux window running `claude --dangerously-skip-permissions --model opus` (override with `WT_CLAUDE=…` or `WT_MODEL=…`)

`wt` resolves its arg against `$TICKETS_DIR` (default `~/.claude/tickets`; zsh `chpwd` hook scopes it to `~/.claude/tickets/<project>/` inside a repo) as a filename slug, a `linear:` breadcrumb, or an epic folder name (in that order). Brief missing → lane asks you to `/scope` it first.

Modes:

| Mode | When |
| --- | --- |
| `wt <slug>` | Single one-shot lane. Default. |
| `wt --loop <slug>` | Outer shell loop wrapping `claude --print` iterations bridged by auto-handoff docs. Stays autonomous past the turn-20 halt. |
| `wt --ralph <epic-slug>` | Ralph autonomous loop for epics — one story per fresh-context iteration, memory via git + `progress.txt` + `prd.json`. |
| `wt --dag <slug>` | Parse plan DAG, spawn ready-set lanes (dormant until prereqs done). |
| `wt --branch <name>` | Spawn a lane on an existing branch (e.g. a PR head). |

Layout default = new tmux window; override `WT_LAYOUT=pane|session`. Monitor pane attaches automatically (`scripts/lane-watch.sh`); opt out with `WT_NO_WATCH=1`.

`wt-gc` reaps lanes whose worktree is gone or whose claude PID is dead.

## Workflow

The filesystem is the database — there is no external tracker. Briefs live in `$TICKETS_DIR/<area>/` (centralized layout: `~/.claude/tickets/<project>/<area>/`); a single ticket is a `<slug>.md`, an epic is a folder with an `_epic.md`. Contract: `$TICKETS_DIR/README.md`.

```
/scope <free text>           → engineer a local brief at $TICKETS_DIR/<area>/<slug>.md
                               (single ticket, or an _epic.md + NN-<child>.md folder)
tix                          → terminal ticket explorer (github.com/gitpancake/tix).
                               status: derivation runs via $TIX_PRELOAD_HOOK →
                               claude/scripts/ticket-status-sync.py.
                               p pickup → wt · e $EDITOR · R/n /rescope|/scope via claude
                               +/− priority · d done · x cancel · N paste from clipboard
wt <slug>                    → autonomous lane (see "Parallel worktree lanes")
/pickup <slug> <BASE> [ctx]  → wt wrapper: sync to a base branch + fold in extra context
/epic <epic-slug> <BASE>     → confirm an epic's ordered story list, then spawn a Ralph lane
/ship                        → commit + push + PR + repo-appropriate review (Claude only for cartage-agent tix tasks)
/address-feedback <PR#>      → triage PR comments, spawn a lane on the PR's branch
/resume [desc]               → resume from the most recent handoff doc
/rebase                      → rebase onto base, auto-resolve trivial conflicts
/simplify                    → review recently changed code for reuse + quality
/retrospective               → retro on completed work
/self-audit                  → claude config + 7d session usage audit
/explain-flow <Q>            → wraps Agent(Explore) with org preamble prepended
/rescope                     → refine an existing brief with new notes
```

Lane stops only on (1) PR + required repo review triggered or explicitly skipped, or (2) genuine blocker. Tix repo review policy: only `cartage-agent` gets `@claude review`; other tix repos skip Claude review. Watch the agent board — red row → look. Otherwise leave it alone. At the context threshold, `/handoff` to a fresh session instead of compacting.

## Cost awareness

Three layers of friction keep heavy Opus usage from silently draining Max-plan buckets.

**Passive — Statusline.** `statusline-command.sh` renders the bottom bar: color-coded context-window bar, plus 5-hour and 7-day usage buckets that appear once either crosses 50%.

```
[████░░░░░░░░░░░░░░░░] 110k/1M 11%                             # quiet
[█████████████████░░░] 850k/1M 85% │ 5h 72% 1h 20m             # loud
```

**Reactive — Post-mortem.** `transcript-costs.sh [days=7] [top=10]` ranks sessions by estimated cost using Anthropic list prices per model.

**Preventive — Hook.** `hooks/tool-loop-warn.sh` fires a one-time warning per session when the same tool has been called ≥30× or total tool calls cross 100. `CLAUDE.md` instructs Claude to propose the **batch pattern** (one LLM call → plan, script applies) before any N-item operation.

Model selection:
- **Opus** — everything. Workflow (local briefs, fresh-context Ralph loops, `/handoff`) is context-efficient enough.
- **Haiku** — bulk mechanical edits only (20+ identical changes).

## Turn-cap protocol

`hooks/turn-cap-warn.sh` hard-halts at turn 20. Soft warn at turn 15. `hooks/auto-handoff.sh` writes `~/.claude/handoffs/<UTC>-auto-<branch>.md` at turn 20 (or ctx ≥300k) so `/clear` is safe and `/resume` has a target. `hooks/clear-handoff.sh` (SessionEnd, `reason=clear`) captures state on any `/clear` ≥5 turns / ≥100k ctx, even below the cap. `hooks/handoff-gate.sh` (PreToolUse) blocks tools at turn ≥20 until a handoff doc exists. Doc format is shared via `hooks/_handoff-doc.sh`.

Behavior by cwd at turn 20:

| Where | Action |
| --- | --- |
| Normal session | Tell user `/clear`. No tools. |
| `wt` lane (`<repo>/.claude/worktrees/`) | One `git add -A && git commit` max, then stop. User runs `/resume` in fresh lane. |
| Ralph lane (lane + `scripts/ralph/`) | End iteration silently. `ralph.sh` spawns next w/ fresh ctx. |

`hooks/debug-router.sh` (UserPromptSubmit) — routes free-form debug prompts ("why is PR #X failing", "tests failing") to `/why-failing` or the `diagnose` skill, once per session.

## Lane state machine

`<wt>/.claude/agent-state` is the single source of truth for `tmux/agent-board.sh`. Writers:

| Hook / script | Writes |
| --- | --- |
| `hooks/agent-state-active.sh` (PreToolUse) | `ACTIVE:<tool>` |
| `hooks/agent-state-idle.sh` (Stop) | `IDLE` |
| `hooks/agent-state-waiting.sh` (Notification) | `WAITING:<code>:<detail>` |
| `hooks/precheck-stop.sh` (Stop) | Forks `<wt>/.claude/precheck.sh` → `RUNNING:precheck` → `DONE` / `FAILED:<step>` |
| `scripts/lane-pause.sh <code> <detail>` | Call before pausing for human input. Vocab: `agent-state-vocab.md`. |

## Org context (not committed)

`~/.claude/org/<org-name>/` holds private, per-organisation engineering context Claude loads when working in that org's codebase. Never symlinked or committed.

```
~/.claude/org/
└── <org-name>/
    ├── context.md    # Full reference: stack, norms, culture, team
    └── preamble.md   # Condensed version injected into subagent prompts
```

Session start → match `org/` folder → load `context.md`. Subagent dispatch → prepend `preamble.md` so org standards travel with the agent.

## Editing

- After changing `CLAUDE.md` — no reload, read at session start.
- After changing `settings.json` — restart open Claude Code sessions.
- After changing a hook — next event picks it up.
- Keep `statusline-command.sh` fast; runs on every refresh.

## Gotchas

- **Node-based hooks need `node` on `/bin/sh` PATH.** Claude Code spawns hooks under `/bin/sh`, which never sources `.zshrc` — so nvm's lazy zsh loader doesn't apply. Plugin hooks shipped as `.mjs` (e.g. omc, anything wrapping `node "$CLAUDE_PLUGIN_ROOT"/…`) fail silently with `node: command not found`. Fix once: symlink nvm's node into a homebrew PATH dir.
  ```bash
  ln -s ~/.nvm/versions/node/<version>/bin/node /opt/homebrew/bin/node
  ln -s ~/.nvm/versions/node/<version>/bin/npm  /opt/homebrew/bin/npm
  ln -s ~/.nvm/versions/node/<version>/bin/npx  /opt/homebrew/bin/npx
  ```
  Re-link after `nvm use` switches versions.
- **Marketplace hooks fire from `extraKnownMarketplaces`, not just `enabledPlugins`.** Registering a marketplace that ships a `hooks/hooks.json` is enough to attach its per-event commands — disabling individual plugins doesn't stop them. Audit before adding new marketplaces; remove the `extraKnownMarketplaces` entry to fully detach.
