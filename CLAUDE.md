# CLAUDE.md

## Project Overview

Personal dotfiles for macOS and WSL2 (Ubuntu). Symlinked into `$HOME` by `install-mac.sh` / `install.sh`. Use `rewire-symlinks.sh` to re-link without re-running the full installer.

Most surface area is documented in subdirectory READMEs:

- `README.md` — top-level: tree, lane workflow, agent board, slack TLDR, art tooling
- `pi/README.md` — Pi config layout (settings, keybindings, extensions, prompts, skills, themes)
- `claude/README.md` — Claude Code config layout (settings, hooks, agents, commands)
- `tmux/README.md` — tmux config + status bar
- `scripts/README.md` — terminal art toys + reactive matrix protocol

This file is the project memory layer for Claude — it captures the gotchas and editing rules that aren't obvious from the source.

## Symlink Layout

`install.sh` / `install-mac.sh` use `ln -sf`. Editing files in this repo updates the live config — no rebuild step. Touch points:

- `~/.zshrc`, `~/.zshenv` → `zsh/.zshrc`, `zsh/.zshenv`
- `~/.config/ghostty/config` → `ghostty/config` (primary terminal — replaced Alacritty 2026-05-27 over recurring memory-leak crashes; see alacritty/alacritty#8727)
- `~/.tmux.conf`, `~/.tmux/tmux-status.sh` → `tmux/` (lane-orchestration `~/.tmux/agent-board.sh` now owned by [wt-lanes](https://github.com/gitpancake/wt-lanes))
- `~/.claude/CLAUDE.md`, `settings.json`, `agents/`, `commands/`, `hooks/`, `scripts/`, `skills/`, `bin/` → `claude/` (some `hooks/`, `scripts/`, `bin/` entries now come from wt-lanes — both repos write into the same target dirs)
- `~/.pi/agent/AGENTS.md`, `settings.json`, `keybindings.json`, `extensions/`, `prompts/`, `skills/`, `themes/`, `bin/` → `pi/`; private Pi runtime state stays outside git (`auth.json`, `.env.local`, `sessions/`, `npm/`, `git/`)
- `~/.dotfiles/scripts/*` is on PATH via `.zshenv` so `slack-watch`, `slack-tldr` etc. resolve from any cwd
- `~/Library/LaunchAgents/local.*.plist` → `claude/local.*.plist` (user agents)

`rewire-symlinks.sh` re-runs the symlinking pass alone. Use after adding a new file under a managed dir.

## Claude Code: subagents vs slash commands

Easy to confuse — they're different things:

- `claude/agents/*.md` are **subagents** dispatched via the Agent tool with `subagent_type: "<name>"`. Available: `backend`, `frontend`, `infra`, `bugfinder`. (Dropped 2026-05-26: `database`, `fullstack`, `plan-lint`, `verifier` — lane IS those layers; self-delegation = ctx burn. 7d data showed 0 lane invocations.)
- `claude/commands/*.md` are **slash commands** typed by the user. Available: `/scope`, `/rescope`, `/pickup`, `/epic`, `/ship`, `/address-feedback`, `/resume`, `/retrospective`, `/rebase`, `/rebase-all`, `/why-failing`. (Dropped 2026-05-26: `/simplify`, `/verify`, `/explain-flow`, `/ryder-docs` — 0 uses in 7d.)
- `claude/skills/*/SKILL.md` are **skills** — symlinked into `~/.claude/skills/`. Available: `grill-with-docs`, `to-issues`, `tdd`, `diagnose`, `handoff`.

Slash commands often dispatch subagents internally, but they aren't the same registry.

## Lane orchestration — owned by wt-lanes

Lane infrastructure (`wt`, `wt-gc`, `agent-board`, state-writer hooks, lane-watch, lane-pause, dag-parse) now lives in [gitpancake/wt-lanes](https://github.com/gitpancake/wt-lanes). Install: `git clone https://github.com/gitpancake/wt-lanes ~/.wt-lanes && ~/.wt-lanes/install.sh`. Its install.sh symlinks files into the same `~/.claude/scripts`, `~/.claude/hooks`, `~/.local/bin`, and `~/.tmux/` namespaces as the dotfiles, alongside the bits still here.

`ticket-status-sync.py` was sunset (2026-06-16). `status:` in `~/.claude/tickets` is now a hand-driven frontmatter field (set directly, or via tix's `d`/`x` pins) — nothing auto-derives it from worktrees/PRs anymore. The `TIX_PRELOAD_HOOK` / `WT_TICKET_SYNC` env vars are gone from `zsh/.zshenv`; tix and wt no longer rewrite `status:`.

For lane semantics (state machine vocab, monitor pane contract), read wt-lanes' own README + CLAUDE.md. (Ralph loop retired 2026-06-09 — epics now run as sequential single lanes via /epic.) Don't duplicate that doctrine here.

## Context-cap + handoff hooks

Caps are context-based, not turn-based — `turn-cap-warn.sh` retired 2026-06-09 (fired once in 14d; lanes run 300+ assistant msgs per user turn, invisible to UserPromptSubmit). Registered hooks (see `claude/settings.json` — that list is the truth, this section just annotates it):

- `lane-ctx-nudge.sh` (PostToolUse) — lane-only, non-blocking. Reads the last billed ctx from the transcript *tail* (never full-file jq); injects a handoff reminder once per tier at 130K/160K/190K. Tier130 is phase-aware (2026-06-10): a review-only remainder means finish the loop + `lane-done.sh`, never hand off — a lane once stopped at 130K right before its review poll and stranded PR #143. Handoff = `/handoff` + wt-lanes' `lane-handoff.sh <doc>` as the lane's final tool call; the `HANDOFF:<doc>` state is what `lane-run.sh` (wt-lanes) keys on to respawn a fresh session that `/resume`s the doc — without it nothing respawns. Cockpit sessions untouched. Motivated by the 14d audit: 107 sessions peaked >150K ctx, <50% handed off, ~39% of cache-read spend bought past 150K.
- `clear-handoff.sh` (SessionEnd, `session_end_reason=="clear"`) — captures state on **any** `/clear` when turns ≥5 **or** ctx ≥100k. Turn count is derived from the transcript (the retired turn-cap hook was the old counter writer). Skips trivial sessions and no-ops if a handoff already exists (marker `session-<id>.handoff`). Sources `claude/hooks/_handoff-doc.sh` (`write_handoff_doc` + `effective_ctx_tokens`) for the doc format.

Nothing blocks tools and nothing auto-writes a doc mid-session — nudges are ambient, `/handoff` stays deliberate, `clear-handoff` is the capture net. The old auto-recycle stack (`auto-handoff.sh`, `handoff-gate.sh`, `tool-loop-warn.sh`) stays dead.

## Debug-intent router

`claude/hooks/debug-router.sh` (UserPromptSubmit) — when a prompt reads like a free-form debugging request ("why is PR #X failing", "tests failing", "broken"), emits a `systemMessage` + `additionalContext` routing to `/why-failing` (failing PR/CI) or the `diagnose` skill (local repro→fix loop). Once per session; skips prompts that already start with a slash command. Closes the adoption gap the self-audit found — 18 debug openers in 7d, `/why-failing` invoked zero times.

## Lane memory caps

Lane Claudes spawned via `wt` route through `claude/bin/claude-lane` (via `$WT_CLAUDE` in zshenv). The launcher does three things vs raw `claude`:

1. **`ulimit -t 1800`** — per-process CPU cap (30min). Inherited by all descendants (RLIMIT_CPU preserved across fork+exec). Counted per-process, so each `tsc --noEmit` gets its own clock — won't kill a healthy long-running session, will reap a runaway typecheck.
2. **`PATH=~/.claude/lane-bin:$PATH`** — slots a `bun` shim ahead of the real one that wraps invocations in `timeout 300`. Cartage's `bun type-check` (= `tsc --noEmit`) peaks at ~4.4 GB RSS; the shim ensures it can't outlive its lane Claude. The shim resolves the real `bun` by walking PATH and skipping its own dir, so it doesn't recurse.
3. **`--strict-mcp-config --mcp-config ~/.claude/mcp.lane.json`** — drops **every** MCP server for lane work (config is an empty `mcpServers`). Stdio ones save ~5 node procs × 50–100 MB per lane; HTTP ones (linear-server, sentry) were dropped 2026-06-09 after 7d of lane transcripts showed 0 calls — and Linear is doctrine-banned in lanes anyway (write-only via `linear-ticket.py`).

Plus `hooks/lane-reaper.sh` runs at SessionEnd: if cwd is inside `.claude/worktrees/`, it SIGTERMs any `tsc/vitest/jest/playwright` proc whose own cwd lives under the lane (3s grace, then SIGKILL). Covers the orphan-after-crash case the ulimit can't catch — e.g. Claude SIGKILL'd while child build was mid-flight and reparented to launchd. macOS bash 3.2 compatible (no `mapfile`). Logs to `~/.claude/logs/lane-reaper.log`.

Cap is per-lane; concurrent lane count is intentionally uncapped.

## Worktree write guard

`claude/hooks/worktree-write-guard.sh` (PreToolUse) — kills the recurring wt-lane **cwd→main leak**: a lane runs with cwd in its worktree but an Edit/Write fires with an absolute path rooted at the main checkout (or a sibling lane), so the edit lands outside the lane while the branch looks clean. Engages only for write tools (Edit/Write/NotebookEdit/MultiEdit) **and** only when cwd is a linked worktree (`git-dir != git-common-dir`). Blocks (exit 2) when the canonical target is under the main checkout but not under the current worktree — sibling worktrees caught for free. Passes relative paths, in-lane abs paths, `~/.claude/tickets` briefs, `/tmp`, and any normal main-repo session. Pure shell + one `python3 realpath` (resolves non-existent Write targets).

## Linear ticket guard

`claude/hooks/linear-ticket-guard.sh` (PreToolUse) — closes the **scope→Linear leak**: free-form work calling `~/.dotfiles/scripts/linear-ticket.py create` directly, producing orphan Linear issues with no PR, no `$TICKETS_DIR` brief, no local home. Doctrine: Linear is a write-only sink touched only by `/ship` (PR's reference ticket) and the `bugfinder` agent (one ticket per confirmed bug). Authorization is by inline env — the authorized call sites prefix the command with `LINEAR_TICKET_CREATE_OK=1` and pass through; any other invocation is blocked (exit 2) with a corrective message pointing back at `$TICKETS_DIR` + `/ship`. Subcommands other than `create` (e.g. `comment`, `update`) pass — that's the agent-comment path. Engages only for Bash tool calls.

## Editing rules

- `zsh/*.zsh*`: `zsh -n <file>` to syntax-check after editing.
- `claude/statusline-command.sh`: keep fast — runs on every Claude Code refresh.
- `tmux/tmux-status.sh`: keep fast — runs every 5s (`status-interval 5`).
- `claude/CLAUDE.md` (the global one, not this file): edits land instantly — Claude reads it at session start. No reload needed.
- `claude/settings.json`: restart open Claude sessions after editing.
- `claude/hooks/*.sh`: next event picks them up — no restart.

## Color thresholds (shared)

`tmux/tmux-status.sh` and `claude/statusline-command.sh` use the same severity scale so the desktop reads consistently:

| Range | Color |
| --- | --- |
| 0–25% | green |
| 26–50% | yellow |
| 51–75% | orange |
| 76–100% | red |

Battery is inverted (low = red).

## Privacy

- `~/.claude/org/<org>/` is gitignored — never committed.
- `scripts/*.config.local` files are gitignored — copy `*.config.example.json` to seed.
- `scripts/redact_chatlogs.py` scrubs `~/.claude/projects/` transcripts before sharing.

## Known quirks

- Target systems: macOS (uses `pmset` for battery) and WSL2/Linux (`/sys/class/power_supply/BAT1/capacity`).
- The zsh theme uses `add-zsh-hook precmd` to print the status bar (not `PROMPT`, to avoid cursor issues).
- Claude statusline keys session timers by `$PPID` so multiple concurrent sessions don't clobber each other's 5h/7d counters.
- `.zshrc` has a duplicate `brew shellenv` line (~116-118) — harmless but could be cleaned up.
- `wt` lanes get per-lane ports `3100 + lane_index` written to `<wt>/.env.local.port`. Dev servers must read `PORT` from there, never hardcode.
- `node_modules` is per-worktree — first action in a fresh lane is usually `bun install`.
- ASCII art toys (`scripts/{hologram,city,ourman}.py`) are launched by the `art` zsh function, which resolves `art <name>` to `~/.local/share/art/<name>.py` (defaults to `hologram`). That dir is **hand-symlinked and installer-unmanaged** — neither `install*.sh` nor `rewire-symlinks.sh` populates it. A new toy needs a manual `ln -sf ~/.dotfiles/scripts/<name>.py ~/.local/share/art/`; without the link `art <name>` reports `Unknown art` even though the script is committed.
