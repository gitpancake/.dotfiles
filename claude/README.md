# claude

Configuration, hooks, agents, and tooling for [Claude Code](https://claude.com/claude-code). Symlinked into `~/.claude/` by the installers.

## Files

| File | Purpose |
| --- | --- |
| `settings.json` | Claude Code settings: enabled plugins, statusline command, hooks, model, permission defaults. |
| `CLAUDE.md` | **Global instructions** loaded into every Claude session — workflow rules, code-quality principles, cost discipline, OpenViking protocol, agent routing. |
| `statusline-command.sh` | Renders Claude Code's bottom status bar: context-window usage bar + 5h/7d rate-limit alerts, color-coded by severity. |
| `transcript-costs.sh` | Post-mortem tool: ranks recent Claude Code sessions by cost so you can spot expensive transcripts. |
| `ralph/` | Vendored Ralph autonomous-loop orchestrator (`ralph.sh` + `CLAUDE.md.template`). Not symlinked — `bin/ralph-bootstrap` copies it into target repos. |
| `local.claude-plan-prune.plist` | launchd job: prunes old plan files from `~/.claude/plans/`. |
| `local.claude-transcript-prune.plist` | launchd job: prunes old transcript files. |

## Subdirectories

| Dir | What's in it |
| --- | --- |
| `agents/` | Specialist subagent profiles — `backend`, `frontend`, `database`, `fullstack`, `platform`, `infra`, `deploy`, `bugfinder`, `plan-lint`, `verifier`. Dispatched via the Agent tool. |
| `commands/` | Global slash commands available in every project (e.g. `/scope`, `/ship`, `/simplify`). |
| `skills/` | Cherry-picked `mattpocock/skills` — `grill-with-docs`, `to-issues`, `tdd`, `diagnose`, `handoff`. Each is a dir with `SKILL.md`; symlinked into `~/.claude/skills/`. |
| `hooks/` | Shell hooks invoked by Claude Code on session events (notifications, tool use, etc.). |
| `scripts/` | Helper scripts called by hooks / commands. |
| `ralph/` | Vendored Ralph loop — see Files table above. |

## Org Context (not committed)

`~/.claude/org/<org-name>/` holds private, per-organisation engineering context that Claude loads when working in that org's codebase. Never symlinked or committed — lives only on the local machine.

```
~/.claude/org/
└── <org-name>/
    ├── context.md    # Full reference: stack, norms, culture, team
    └── preamble.md   # ~40-line condensed version injected into subagent prompts
```

**How it's used:**
- At session start, Claude checks for a matching `org/` folder and loads `context.md`.
- When dispatching a subagent, `preamble.md` is prepended to the subagent prompt so it inherits org-specific engineering standards.

To add a new org, create `~/.claude/org/<name>/context.md` and `preamble.md` — no config changes needed.

## Hooks

Wired in `settings.json`:

| Event | Script | What it does |
| --- | --- | --- |
| `Notification` | `tmux-bell.sh` | Rings the tmux bell so the user notices Claude needs input. |
| `PostToolUse` (any) | `tool-loop-warn.sh` | Emits a `systemMessage` once per session at 30× same-tool calls or 100 total — a nudge to consider the batch pattern or `/clear`. |

## Statusline

`statusline-command.sh` reads the JSON Claude Code pipes on stdin and prints:

```
[████████░░░░░░░░░░░░] 320k/1M 32% │ 5h 67% 2h 14m
```

Context bar always shown. Rate-limit buckets only appear once usage ≥ 50%.

## Editing

- After changing `CLAUDE.md`, no reload needed — Claude reads it at session start.
- After changing `settings.json`, restart any open Claude Code sessions.
- After changing a hook, the next event picks it up — no restart needed.
- Keep `statusline-command.sh` fast; it runs on every refresh.
