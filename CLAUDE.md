# CLAUDE.md

## Project Overview

Personal dotfiles for macOS and WSL2 (Ubuntu). Symlinked into `$HOME` by `install-mac.sh` / `install.sh`. Use `rewire-symlinks.sh` to re-link without re-running the full installer.

Most surface area is documented in subdirectory READMEs:

- `README.md` — top-level: tree, lane workflow, agent board, slack TLDR, focus-guard, art tooling
- `claude/README.md` — Claude Code config layout (settings, hooks, agents, commands)
- `tmux/README.md` — tmux config + status bar
- `scripts/README.md` — terminal art toys + reactive matrix protocol
- `focus-guard/README.md` — site blocker setup

This file is the project memory layer for Claude — it captures the gotchas and editing rules that aren't obvious from the source.

## Symlink Layout

`install.sh` / `install-mac.sh` use `ln -sf`. Editing files in this repo updates the live config — no rebuild step. Touch points:

- `~/.zshrc`, `~/.zshenv` → `zsh/.zshrc`, `zsh/.zshenv`
- `~/.tmux.conf`, `~/.tmux/agent-board.sh`, `~/.tmux/tmux-status.sh` → `tmux/`
- `~/.claude/CLAUDE.md`, `settings.json`, `agents/`, `commands/`, `hooks/`, `scripts/`, `skills/`, `bin/` → `claude/`
- `~/.dotfiles/scripts/*` is on PATH via `.zshenv` so `slack-watch`, `slack-tldr` etc. resolve from any cwd
- `~/Library/LaunchAgents/local.*.plist` → `claude/local.*.plist` (user agents)
- focus-guard plists are **LaunchDaemons** — `install-mac.sh`/`rewire-symlinks.sh` *copy* (not symlink) `focus-guard/local.focus-*.plist` → `/Library/LaunchDaemons/` (root) and `bootstrap` them; scripts copied to `/usr/local/bin`. Editing the repo files does **not** hot-update — re-run install or `sudo rewire-symlinks.sh`.

`rewire-symlinks.sh` re-runs the symlinking pass alone. Use after adding a new file under a managed dir.

## Claude Code: subagents vs slash commands

Easy to confuse — they're different things:

- `claude/agents/*.md` are **subagents** dispatched via the Agent tool with `subagent_type: "<name>"`. Available: `backend`, `frontend`, `database`, `fullstack`, `platform`, `infra`, `deploy`, `bugfinder`, `plan-lint`, `verifier`.
- `claude/commands/*.md` are **slash commands** typed by the user. Available: `/scope`, `/rescope`, `/pickup`, `/epic`, `/ship`, `/address-feedback`, `/resume`, `/simplify`, `/retrospective`.
- `claude/skills/*/SKILL.md` are **skills** — symlinked into `~/.claude/skills/`. Available: `grill-with-docs`, `to-issues`, `tdd`, `diagnose`, `handoff`.

Slash commands often dispatch subagents internally, but they aren't the same registry.

## Ralph autonomous loop

`claude/ralph/` holds the vendored `ralph.sh` orchestrator + `CLAUDE.md.template` (Ralph's per-iteration prompt). It is **not** symlinked — `claude/bin/ralph-bootstrap` copies it into a target repo/worktree's `scripts/ralph/` and excludes that dir from git so the loop's runtime churn (`prd.json`, `progress.txt`, `archive/`) never lands on the feature branch. `wt --ralph` runs the bootstrap + loop inside a lane.

One epic shape feeds the loop. An epic is a folder with an `_epic.md`; its `<!-- epic-stories -->` block carries the authoritative, human-confirmed ordered story list. `/epic <epic-slug> <BASE>` confirms that list and spawns the lane — at spawn, `claude/scripts/epic-parse.sh` projects `_epic.md` into `scripts/ralph/prd.json` inside the worktree. `ralph.sh` then grinds one story per fresh-context iteration (memory via git + `progress.txt` + `prd.json`), executing the confirmed list — it never decomposes.

## Lane observability — monitor pane

Policy: **no lane runs unmonitored.** Every `wt` spawn auto-attaches a split-pane monitor running `claude/scripts/lane-watch.sh <wt>`. The watcher polls every 10s and renders:

- **Ralph lane** (scripts/ralph/ present): story-completion table from `userStories[].passes`, iteration count, tail of `iterations/latest.log`. Notifies on each story completion + overall done.
- **Generic lane**: agent-state, ctx tokens, branch, last 5 commits, short git status. Notifies on `WAITING:*` transitions.

Layout: ralph and non-ralph lanes alike get a 35% right-side pane (in `window` and `session` modes) or a vertical split-below (in `pane` mode). Opt out per spawn with `WT_NO_WATCH=1` — but the default is monitored, intentionally.

Why strict: orchestrator agents previously lost track of spawned lanes (nohup detach, no scrollback). The pane is the visible contract. Notifications fire via `terminal-notifier` / `osascript` so the user knows the moment a lane hits `WAITING` or completes.

## Lane state machine

`<wt>/.claude/agent-state` is the single source of truth for `agent-board.sh`. Writers:

- `claude/hooks/agent-state-active.sh` (PreToolUse) → `ACTIVE:<tool>`
- `claude/hooks/agent-state-idle.sh` (Stop) → `IDLE`
- `claude/hooks/agent-state-waiting.sh` (Notification) → `WAITING:<code>:<detail>`
- `claude/hooks/precheck-stop.sh` (Stop) → forks `<wt>/.claude/precheck.sh` which writes `RUNNING:precheck` → `DONE` / `FAILED:<step>`
- `claude/scripts/lane-pause.sh <code> <detail>` — call before pausing for human input to tag a reason code (vocab in `claude/agent-state-vocab.md`)

`agent-board.sh` self-heals: if the recorded `<wt>/.claude/agent-pid` is dead, it resets the row to `IDLE` and preserves mtime. CTX column reads `~/.claude/projects/<encoded>/*.jsonl` and caches by jsonl mtime+size.

## Auto-handoff (turn-cap fallback)

`claude/hooks/auto-handoff.sh` (UserPromptSubmit, runs after `turn-cap-warn.sh`) — at turn ≥50, mechanically dumps last prompts + tool calls + active files + git state to `~/.claude/handoffs/<UTC>-auto-<branch>.md` and announces the path via `systemMessage`. Fires once per session (sentinel reuses `${TMPDIR}/claude-turn-cap-warn/session-<id>.warned`). Belt-and-suspenders for the documented turn-cap protocol — handoff doc exists *before* `/clear` is plausible, so /resume has a target even when the warning was ignored. Pure shell — no LLM call, no compliance dependency.

## Editing rules

- `zsh/*.zsh*`: `zsh -n <file>` to syntax-check after editing.
- `claude/statusline-command.sh`: keep fast — runs on every Claude Code refresh.
- `tmux/tmux-status.sh`: keep fast — runs every 5s (`status-interval 5`).
- `tmux/agent-board.sh`: keep fast — pinned in a `watch -n2` pane. CTX column already caches via `<wt>/.claude/ctx-cache`; preserve that contract for any new per-row data.
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
- `/etc/hosts.blocked` (focus-guard's real domain list) is OS-side only — never committed. `focus-guard/hosts.blocked.example` is the template.
- `scripts/*.config.local` files are gitignored — copy `*.config.example.json` to seed.
- `scripts/redact_chatlogs.py` scrubs `~/.claude/projects/` transcripts before sharing.

## Known quirks

- Target systems: macOS (uses `pmset` for battery) and WSL2/Linux (`/sys/class/power_supply/BAT1/capacity`).
- The zsh theme uses `add-zsh-hook precmd` to print the status bar (not `PROMPT`, to avoid cursor issues).
- Claude statusline keys session timers by `$PPID` so multiple concurrent sessions don't clobber each other's 5h/7d counters.
- `.zshrc` has a duplicate `brew shellenv` line (~116-118) — harmless but could be cleaned up.
- `wt` lanes get per-lane ports `3100 + lane_index` written to `<wt>/.env.local.port`. Dev servers must read `PORT` from there, never hardcode.
- `node_modules` is per-worktree — first action in a fresh lane is usually `bun install`.
