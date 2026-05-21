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
- `~/.tmux.conf`, `~/.tmux/tmux-status.sh` → `tmux/` (lane-orchestration `~/.tmux/agent-board.sh` now owned by [wt-lanes](https://github.com/gitpancake/wt-lanes))
- `~/.claude/CLAUDE.md`, `settings.json`, `agents/`, `commands/`, `hooks/`, `scripts/`, `skills/`, `bin/` → `claude/` (some `hooks/`, `scripts/`, `bin/` entries now come from wt-lanes — both repos write into the same target dirs)
- `~/.dotfiles/scripts/*` is on PATH via `.zshenv` so `slack-watch`, `slack-tldr` etc. resolve from any cwd
- `~/Library/LaunchAgents/local.*.plist` → `claude/local.*.plist` (user agents)
- focus-guard plists are **LaunchDaemons** — `install-mac.sh`/`rewire-symlinks.sh` *copy* (not symlink) `focus-guard/local.focus-*.plist` → `/Library/LaunchDaemons/` (root) and `bootstrap` them; scripts copied to `/usr/local/bin`. Editing the repo files does **not** hot-update — re-run install or `sudo rewire-symlinks.sh`.

`rewire-symlinks.sh` re-runs the symlinking pass alone. Use after adding a new file under a managed dir.

## Claude Code: subagents vs slash commands

Easy to confuse — they're different things:

- `claude/agents/*.md` are **subagents** dispatched via the Agent tool with `subagent_type: "<name>"`. Available: `backend`, `frontend`, `database`, `fullstack`, `platform`, `infra`, `deploy`, `bugfinder`, `plan-lint`, `verifier`.
- `claude/commands/*.md` are **slash commands** typed by the user. Available: `/scope`, `/rescope`, `/pickup`, `/epic`, `/ship`, `/address-feedback`, `/resume`, `/simplify`, `/retrospective`, `/rebase`, `/rebase-all`, `/verify`, `/why-failing`, `/explain-flow`, `/ryder-docs`.
- `claude/skills/*/SKILL.md` are **skills** — symlinked into `~/.claude/skills/`. Available: `grill-with-docs`, `to-issues`, `tdd`, `diagnose`, `handoff`.

Slash commands often dispatch subagents internally, but they aren't the same registry.

## Lane orchestration — owned by wt-lanes

Lane infrastructure (`wt`, `wt-gc`, `ralph-bootstrap`, `agent-board`, state-writer hooks, Ralph orchestrator, lane-watch, lane-pause, epic-parse, dag-parse) now lives in [gitpancake/wt-lanes](https://github.com/gitpancake/wt-lanes). Install: `git clone https://github.com/gitpancake/wt-lanes ~/.wt-lanes && ~/.wt-lanes/install.sh`. Its install.sh symlinks files into the same `~/.claude/scripts`, `~/.claude/hooks`, `~/.local/bin`, and `~/.tmux/` namespaces as the dotfiles, alongside the bits still here.

This repo still owns `claude/scripts/ticket-status-sync.py` (status derivation). Both the tix preload (`$TIX_PRELOAD_HOOK`) and wt spawn (`$WT_TICKET_SYNC`) point at it — both env vars exported from `zsh/.zshenv`.

For lane semantics (state machine vocab, monitor pane contract, Ralph loop), read wt-lanes' own README + CLAUDE.md. Don't duplicate that doctrine here.

## Turn-cap + handoff hooks

Turn cap is **20 across the board** (was 30 halt / 50 gate). Soft nudge at 15. Tuned down because the self-audit showed 0% turn-cap obedience and `/clear`-dominant sessions (186 `/clear` vs 4 `/handoff` in 7d) — capture must be automatic, not compliance-dependent. Shared doc generator `claude/hooks/_handoff-doc.sh` (`write_handoff_doc` + `effective_ctx_tokens`) is sourced by both writers below so the handoff format lives in one place.

- `turn-cap-warn.sh` (UserPromptSubmit) — soft reminder at 15; HARD HALT directive at 20, re-fires every turn past 20. cwd-aware (normal / wt lane / Ralph lane).
- `auto-handoff.sh` (UserPromptSubmit, after turn-cap-warn) — at turn ≥20 **or** ctx ≥300k tokens, dumps last prompts + tool calls + active files + git state to `~/.claude/handoffs/<UTC>-auto-<branch>.md`. Once per session (sentinel `${TMPDIR}/claude-turn-cap-warn/session-<id>.warned`, tag `auto-handoff`).
- `clear-handoff.sh` (SessionEnd, `session_end_reason=="clear"`) — captures state on **any** `/clear`, even below the cap, when turns ≥5 **or** ctx ≥100k. Skips trivial sessions and no-ops if a handoff already exists (marker `session-<id>.handoff`). Closes the "/clear at p50≈2 turns loses state" gap the cap can't see.
- `handoff-gate.sh` (PreToolUse) — at turn ≥20 **blocks every tool** (exit 2). One exception: a single work-saving `git status/add/commit` (per-session `.savedone` sentinel; second save blocked too) — push/gh/Edit/Read/Agent/etc. blocked outright. The doc existing is the green light to *recycle*, not to keep working, so the gate no longer self-disables once auto-handoff writes the marker (old bug: marker present → passed forever → interactive lanes ran unbounded, burning context + OAuth quota). Recycle is out-of-process: wt-loop/Ralph spawn the next iteration that `/resume`s the handoff; plain sessions `/clear` + `/resume`.

All pure shell — no LLM call, no compliance dependency. The doc exists *before* `/clear` is plausible, so `/resume` always has a target.

## Debug-intent router

`claude/hooks/debug-router.sh` (UserPromptSubmit) — when a prompt reads like a free-form debugging request ("why is PR #X failing", "tests failing", "broken"), emits a `systemMessage` + `additionalContext` routing to `/why-failing` (failing PR/CI) or the `diagnose` skill (local repro→fix loop). Once per session; skips prompts that already start with a slash command. Closes the adoption gap the self-audit found — 18 debug openers in 7d, `/why-failing` invoked zero times.

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
