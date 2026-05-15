# Dotfiles

Personal dotfiles for macOS and WSL2 (Ubuntu) development environments.

## What's Included

```
dotfiles/
├── zsh/
│   ├── .zshenv                       # Loaded by every zsh session (interactive or not)
│   ├── .zshrc                        # Zsh config (Oh My Zsh, nvm, brew, aliases)
│   └── robbyrussell-bar.zsh-theme    # robbyrussell prompt (clock hook disabled)
├── tmux/
│   ├── .tmux.conf                    # tmux config (keybindings, gruvbox dark theme)
│   ├── tmux-status.sh                # System stats: BAT / CPU / MEM / DSK with
│   │                                 #   dynamic color thresholds
│   ├── agent-board.sh                # Parallel-lane status board: state, age, live
│   │                                 #   context tokens, port (one row per worktree)
│   └── grid-4x2.sh                   # Quick 4×2 tmux pane grid layout
├── claude/
│   ├── settings.json                 # Claude Code settings + plugins
│   ├── CLAUDE.md                     # Global instructions (workflow, cost discipline,
│   │                                 #   subagent routing, local-first planning, OV)
│   ├── statusline-command.sh         # Bottom status: context bar + 5h/7d usage alerts
│   ├── transcript-costs.sh           # Post-mortem: rank sessions by $ cost
│   ├── worktree-protocol.md          # Multi-agent worktree safety rules
│   ├── agent-state-vocab.md          # Reason-code vocab for lane WAITING states
│   ├── agents/                       # Specialist subagents — backend, frontend,
│   │                                 #   database, fullstack, platform, infra, deploy,
│   │                                 #   bugfinder, plan-lint, verifier
│   ├── commands/                     # Slash commands — /scope, /rescope, /pickup, /epic,
│   │                                 #   /ship, /address-feedback, /resume, /simplify,
│   │                                 #   /retrospective
│   ├── skills/                       # Project skills — grill-with-docs, to-issues,
│   │                                 #   tdd, diagnose, handoff
│   ├── ralph/                        # Vendored Ralph loop — ralph.sh + CLAUDE.md.template
│   │                                 #   (copied into target repos by ralph-bootstrap)
│   ├── hooks/                        # Session/tool hooks
│   │   ├── tmux-bell.sh              #   Notification → tmux bell
│   │   ├── tool-loop-warn.sh         #   PostToolUse warning at 30× same / 100 total
│   │   ├── _state-write.sh           #   Shared writer for agent-state file
│   │   ├── _warn-helpers.sh          #   Shared helpers for warning hooks
│   │   ├── agent-state-active.sh     #   PreToolUse → ACTIVE
│   │   ├── agent-state-idle.sh       #   Stop → IDLE
│   │   ├── agent-state-waiting.sh    #   Notification → WAITING:<code>
│   │   ├── precheck-stop.sh          #   Stop → fork .claude/precheck.sh
│   │   └── turn-cap-warn.sh          #   Tiered warnings at 30/50/75/100 turns
│   ├── scripts/                      # Helpers called by commands / hooks
│   │   ├── lane-pause.sh             #   Tag lane WAITING with reason code
│   │   ├── lane-summary.sh           #   LLM 1-line summary of HEAD per lane
│   │   ├── plan-lint.sh              #   Plan-vs-ticket coverage gate
│   │   ├── verify-clean.sh           #   Pre-ship verification entry point
│   │   ├── dag-parse.sh              #   Parse plan slice DAG
│   │   └── prune-plans.sh            #   GC stale ~/.claude/plans/<ID>.md
│   ├── bin/                          # PATH-exposed lane primitives
│   │   ├── wt                        #   Spawn parallel worktree lane (slug / epic resolver)
│   │   ├── wt-gc                     #   Reap dead lanes
│   │   ├── ralph-bootstrap           #   Drop the Ralph loop into a repo/worktree
│   │   ├── tix                       #   Terminal ticket explorer (~/.claude/tickets)
│   │   ├── git-watch                 #   Watch repo HEAD, write art state
│   │   ├── slack-tldr                #   CLI ack/dismiss for Slack TLDR daemon
│   │   └── slack-watch               #   Interactive tmux pane renderer
│   ├── local.claude-plan-prune.plist     # launchd: prune ~/.claude/plans/
│   ├── local.claude-transcript-prune.plist # launchd: prune ~/.claude/projects/*/
│   ├── local.claude-wt-gc.plist          # launchd: reap orphan worktrees
│   └── local.slack-tldr.plist            # launchd: Slack TLDR daemon
│   # ~/.claude/org/ lives outside this repo (gitignored) — per-org engineering
│   # context loaded at session start, never committed.
├── alacritty/
│   ├── alacritty.toml                # Imports a Gruvbox Material theme
│   └── themes/                       # Theme variants (medium dark/light, hard dark)
├── iterm/                            # Gruvbox Material iTerm2 color presets
├── vim/
│   └── .vimrc                        # Minimal vim config
├── focus-guard/
│   ├── focus-guard.sh                # Time-aware /etc/hosts blocker
│   ├── cert-gen.sh                   # mkcert SAN cert for blocked domains
│   ├── focus.conf                    # nginx server blocks (80 + 443)
│   ├── block / unblock               # Manual overrides
│   ├── hosts.blocked.example         # Template (no real domains)
│   └── local.focus-{guard,nginx}.plist
├── scripts/
│   ├── city.py / hologram.py         # Terminal toys
│   ├── tickets-tui.py                # `tix` — keyboard ticket explorer + glow viewer
│   ├── commit-watcher.py             # Drives matrix state from git commits
│   ├── audio-watcher.py              # Audio-event watcher daemon
│   ├── git-watch.py                  # Lightweight git HEAD watcher
│   ├── slack-tldr.py                 # Slack alerts → Haiku TLDR daemon
│   ├── slack-tldr-pane.sh            # Static tmux pane renderer
│   ├── claude_oauth.py               # Claude Code OAuth → Anthropic API helper
│   ├── redact_chatlogs.py            # Regex secret redactor for ~/.claude/projects
│   └── watch.py                      # Generic file-change watcher
├── install.sh                        # Symlink installer (Linux/WSL2)
├── install-mac.sh                    # Symlink installer (macOS)
├── rewire-symlinks.sh                # Re-link without re-running full installer
└── README.md
```

## Setup

### macOS
```bash
git clone git@github.com:gitpancake/.dotfiles.git ~/.dotfiles
cd ~/.dotfiles
chmod +x install-mac.sh
./install-mac.sh
source ~/.zshrc
```

### Linux/WSL2
```bash
git clone git@github.com:gitpancake/.dotfiles.git ~/.dotfiles
cd ~/.dotfiles
chmod +x install.sh
./install.sh
source ~/.zshrc
```

After editing the installer or adding new symlink targets, run `./rewire-symlinks.sh` to re-apply links without a full reinstall.

## Zsh Theme

`robbyrussell-bar` is the stock robbyrussell prompt. The full-width time separator hook is registered but disabled — it actively unregisters on shell start so re-sourcing `.zshrc` will not re-attach a stale clock from a prior session.

```
➜ my-project git:(main) ✗
```

## Tmux

Gruvbox dark theme with intuitive keybindings:

- `|` or `\` to split horizontally, `-` to split vertically
- `Alt+Arrow` to navigate panes, `Ctrl+Left/Right` to switch windows
- `Prefix + t` to set pane title, `Prefix + r` to rename window

System status bar with dynamic colors (green → yellow → orange → red):

```
 S  │  1:zsh   2:vim  │  BAT 85%  │  CPU 12%  │  MEM 43%  │  DSK 2%  │  14:30
```

Thresholds: 0-25% green, 26-50% yellow, 51-75% orange, 76-100% red. Battery is inverted (low = red).

### Agent board (parallel lanes)

`tmux/agent-board.sh` is a single-pane status board for parallel worktree agents. Pin it:

```bash
watch -tcn2 ~/.tmux/agent-board.sh
```

One row per worktree, sorted by urgency, color-coded by state:

```
LANE                          STATE              AGE    CTX    PORT
----------------------------------------------------------------
team-1571 harden webhook        ACTIVE:Bash        0s     231K   3116
team-1568 skip modal no-input   W:ambiguity        4m     78K    3115
team-1555 cleanup auth          DONE               12m    -      3104
```

- **STATE** — `ACTIVE`, `WAITING:<code>`, `RUNNING:precheck`, `FAILED:<step>`, `DONE`, `IDLE`. Codes documented in `claude/agent-state-vocab.md`.
- **AGE** — time since the lane last changed state.
- **CTX** — live context-window tokens for that lane's Claude session, parsed from the latest `~/.claude/projects/<encoded>/*.jsonl`. Cached by jsonl mtime+size so 2s ticks stay cheap.
- **PORT** — per-lane dev-server port (`<wt>/.env.local.port`).

Stale `IDLE` rows hide after 30 min (`BOARD_HIDE_IDLE_AFTER` to override; `BOARD_SHOW_ALL=1` to disable). Liveness check reaps lanes whose `claude` PID is dead — board self-heals to `IDLE` so killed terminals don't pile up red.

## Claude Code: Parallel Worktree Lanes

`claude/bin/wt <slug-or-epic>` spawns one parallel lane per ticket. Each lane is fire-and-forget: it reads the local brief, works it through to a PR, then stops.

What `wt` produces:

- worktree at `<repo>/.claude/worktrees/<slug>`
- branch `<type>/<slug>` off current HEAD
- per-lane port stamped in `.env.local.port` (3099 + lane index)
- `.claude/agent-state` seeded to `IDLE` (visible to `agent-board.sh`)
- new tmux window running `claude --dangerously-skip-permissions --model opus` (override with `WT_CLAUDE=…` or `WT_MODEL=…`)
- `wt` resolves its arg against `~/.claude/tickets/` as a filename slug, a `linear:` breadcrumb, or an epic folder name (in that order). Brief missing → the lane asks you to `/scope` it first.

`wt --ralph <epic-slug>` runs the Ralph autonomous loop inside the lane instead — `ralph-bootstrap` drops `scripts/ralph/` in, `epic-parse.sh` projects the epic's `_epic.md` into `scripts/ralph/prd.json`, then `ralph.sh` grinds one story per fresh-context iteration (memory via git + `progress.txt` + `prd.json`). An epic is a folder with an `_epic.md` carrying a human-confirmed ordered story list; Ralph executes that list and never decomposes. Use `/epic <epic-slug> <BASE>` to confirm the story order and spawn the lane.

Layout default = new tmux window; override with `WT_LAYOUT=pane|session`.

`wt-gc` reaps lanes whose worktree is gone or whose claude PID is dead.

## Claude Code: Workflow

The filesystem is the database — there is no external tracker. Briefs live in `~/.claude/tickets/<area>/`; a single ticket is a `<slug>.md`, an epic is a folder with an `_epic.md`. The whole workflow is local.

```
/scope <free text>           → engineer a local brief at ~/.claude/tickets/<area>/<slug>.md
                               (single ticket, or an _epic.md + NN-<child>.md folder)
tix                          → terminal ticket explorer with split-pane preview.
                               p pickup → wt · e $EDITOR · R/n /rescope|/scope via claude
                               +/− priority · d done · x cancel · N paste from clipboard
wt <slug>                    → autonomous lane: reads the brief, plans slices inline,
                               leans on grill-with-docs / tdd / handoff, commits per layer
/pickup <slug> <BASE> [ctx]  → wt wrapper: sync cockpit to a base branch + fold in extra
                               context, then spawn the lane
/epic <epic-slug> <BASE>     → confirm an epic's ordered story list, then spawn a Ralph lane
wt --ralph <epic-slug>       → Ralph loop in a lane: one story per fresh-context iteration
/ship                        → commit + push + PR + @claude review
/address-feedback <PR#>      → harvests + triages PR comments, spawns a lane on the PR's branch
/resume [desc]               → resume work from the most recent handoff doc
```

Lane stops only on PR + review triggered (success) or genuine blocker. Watch `agent-board.sh` — red row → look. Otherwise leave it alone. At the context threshold, `/handoff` to a fresh session instead of compacting.

## Claude Code: Cost Awareness

Three layers of friction keep heavy Opus usage from silently draining Max-plan buckets.

### Passive — Status line
`claude/statusline-command.sh` renders the Claude Code bottom status bar: a color-coded context-window bar, plus 5-hour and 7-day usage buckets that only appear once either crosses 50%.

```
[████░░░░░░░░░░░░░░░░] 110k/1M 11%                             # quiet
[█████████████████░░░] 850k/1M 85% │ 5h 72% 1h 20m             # loud
```

### Reactive — Post-mortem tool
```bash
~/.claude/transcript-costs.sh [days=7] [top=10]
```
Ranks sessions by estimated API-equivalent cost using Anthropic list prices per model.

### Preventive — CLAUDE.md rule + PostToolUse hook
The `Cost Discipline` section in `claude/CLAUDE.md` instructs Claude to propose the **batch pattern** (one LLM call produces a plan, a script applies it) before any N-item operation.

Model selection:
- **Opus** — everything. The workflow (local briefs, fresh-context Ralph loops, `/handoff`) is context-efficient enough that the sonnet-for-execution hack is retired.
- **Haiku** — bulk mechanical edits only (20+ identical changes).

`claude/hooks/tool-loop-warn.sh` fires a one-time warning per session when the same tool has been called ≥30× or total tool calls cross 100.

## Claude Code: Org Context

`~/.claude/org/<org-name>/` holds private, per-organisation engineering standards loaded automatically — never committed.

```
~/.claude/org/
└── <org-name>/
    ├── context.md    # Full reference: stack, norms, incident culture, team
    └── preamble.md   # Condensed version injected into every subagent prompt
```

At session start Claude checks for a matching `org/` folder and applies it. When dispatching a subagent, `preamble.md` is prepended so org standards travel with the agent.

## Slack Alerts → tmux pane

Daemon subscribes to specific Slack channels via Socket Mode, runs each new message through Haiku for a one-line TLDR, writes the result to a state file rendered in a tmux pane.

**Setup (one-time):**

1. Create a Slack app at <https://api.slack.com/apps> → *From scratch*.
2. **Socket Mode** → enable → generate App-Level Token (`xapp-…`) with scope `connections:write`.
3. **OAuth & Permissions** → Bot Token Scopes: `channels:history`, `groups:history`, `im:history`, `mpim:history`, `channels:read`.
4. **Event Subscriptions** → enable → subscribe bot to `message.channels` (+ `message.groups` / `message.im` if private channels / DMs).
5. *Install to Workspace* → copy Bot Token (`xoxb-…`).
6. `cp scripts/slack-tldr.config.example.json scripts/slack-tldr.config.local` — fill in tokens and the `channels` dict (maps channel names → IDs, split into `alerts` and `monitor` tabs).
7. `/invite @your-bot` in each configured channel. Daemon verifies membership on startup and exits with an error if the bot is missing from any channel.
8. Re-run `./install-mac.sh` (or `./rewire-symlinks.sh`) to install the launchd agent.

**Auth:** API calls use Claude Code OAuth token from macOS keychain (service `Claude Code-credentials`). Falls back to `ANTHROPIC_API_KEY` if missing.

**Pane:** in any tmux pane:

```bash
slack-watch
```

Numbered list of active alerts with timestamps and channel names. New (unacked) alerts blink until you focus the pane and press any key. `q` / Ctrl-C exits.

Static (passive) renderer:

```bash
watch -tcn2 ~/.dotfiles/scripts/slack-tldr-pane.sh
```

**Dismiss / ack:**
```bash
slack-tldr ack           # mark all current alerts seen
slack-tldr dismiss 2     # dismiss the 2nd active alert
slack-tldr dismiss-all   # clear everything
```

**State + logs:**
- `~/.local/share/slack-tldr/state.json` — active alerts + dismissed ring
- `/tmp/slack-tldr.{out,err}` — daemon stdout/stderr

## Reactive Matrix (commit-driven art)

`commit-watcher.py` watches a git remote and pushes palette / intensity / commit log into `~/.local/share/art/state.json`. Any compatible curses renderer can poll that file for coordinated animation.

```bash
cp scripts/commit-watcher.config.example.json scripts/commit-watcher.config.local
$EDITOR scripts/commit-watcher.config.local        # set repo_path + rules
python3 scripts/commit-watcher.py                  # foreground
```

LLM describer: `describer_enabled: true` + `ANTHROPIC_API_KEY`. Cached at `~/.local/share/art/describer-cache/<sha>.txt`. Full schema and burst-trigger details in `scripts/README.md`.

`scripts/git-watch.py` is the lighter-weight cousin — just polls HEAD and writes state, no LLM, no palette logic.

## Audio Watcher

`scripts/audio-watcher.py` is a daemon that watches for audio events (configurable). See `scripts/audio-watcher.config.example.json` for setup.

## Focus Guard

Time-aware site blocker that swaps `/etc/hosts` and serves a status page for blocked domains on both HTTP and HTTPS.

**Focus windows:** Mon–Fri 09:00–18:00, Sat–Sun 11:00–15:00. Outside those hours, sites are unblocked automatically.

**How it works:** nginx runs persistently on ports 80 + 443. `/etc/hosts` redirects blocked domains to `127.0.0.1`, so every request lands on nginx and gets the status page. A mkcert-issued cert (trusted via macOS Keychain) means HTTPS sites show the page cleanly.

**Manual overrides:**
```bash
unblock   # unblock immediately — auto re-blocks within 10 min
block     # re-block immediately
```

**Private:** `/etc/hosts.blocked` (your actual domain list) lives only as a system file and is never committed. `hosts.blocked.example` is the committed template.

**Adding a domain:**
```bash
# Edit /etc/hosts.blocked, then:
sudo cert-gen.sh && sudo /opt/homebrew/bin/nginx -s reload
```

## Secret Redaction

`scripts/redact_chatlogs.py` scrubs Claude session transcripts in `~/.claude/projects/` of common secret patterns (Anthropic / OpenAI / AWS / GitHub / JWT / DB URLs / PEM keys). In-place, regex-based. Run before sharing a transcript.

## Dependencies

- [Oh My Zsh](https://ohmyz.sh/)
- [nvm](https://github.com/nvm-sh/nvm)
- [Homebrew (Linuxbrew)](https://brew.sh/)
- [Claude Code](https://claude.ai/code)
- [jq](https://jqlang.org/) — required by `statusline-command.sh`, `transcript-costs.sh`, `tool-loop-warn.sh`
- [mkcert](https://github.com/FiloSottile/mkcert) + [nginx](https://nginx.org/) — focus-guard only
- Python 3 stdlib (`curses`) — terminal toys
