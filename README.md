# Dotfiles

Personal dotfiles for macOS and WSL2 (Ubuntu) development environments.

## What's Included

```
dotfiles/
├── zsh/
│   ├── .zshenv                       # Loaded by every zsh session (interactive or not)
│   ├── .zshrc                        # Zsh config (Oh My Zsh, nvm, brew, aliases)
│   └── robbyrussell-bar.zsh-theme    # Custom theme with time separator bar
├── tmux/
│   ├── .tmux.conf                    # tmux config (keybindings, gruvbox dark theme)
│   └── tmux-status.sh                # Status bar: battery, CPU, memory, disk
│                                     #   with dynamic color-coded thresholds
├── claude/
│   ├── settings.json                 # Claude Code settings and plugins
│   ├── CLAUDE.md                     # Global instructions (workflow, code quality,
│   │                                 #   cost discipline, OpenViking protocol)
│   ├── statusline-command.sh         # Bottom-bar renderer: context window + 5h/7d
│   │                                 #   usage alerts, color-coded by severity
│   ├── transcript-costs.sh           # Post-mortem: rank recent sessions by $ cost
│   ├── agents/                       # Specialist subagents (backend, frontend,
│   │                                 #   database, fullstack, platform, infra, deploy)
│   ├── commands/                     # Global slash commands (/simplify)
│   └── hooks/
│       ├── tmux-bell.sh              # tmux bell on Notification events
│       └── tool-loop-warn.sh         # PostToolUse warning at 30× same-tool
│                                     #   or 100 total calls per session
├── focus-guard/
│   ├── focus-guard.sh                # Time-aware blocker: swaps /etc/hosts on a
│   │                                 #   10-min cron, writes status page
│   ├── cert-gen.sh                   # Generates mkcert cert covering all blocked
│   │                                 #   domains (regenerates only when list changes)
│   ├── focus.conf                    # nginx server blocks for ports 80 + 443
│   ├── block                         # Manual override: block immediately
│   ├── unblock                       # Manual override: unblock for ~10 min
│   ├── hosts.blocked.example         # Template for /etc/hosts.blocked (no domains)
│   ├── com.henrypye.focus-guard.plist  # launchd: runs focus-guard.sh every 10 min
│   └── com.henrypye.focus-nginx.plist  # launchd: keeps nginx alive on 80 + 443
├── scripts/
│   ├── city.py                       # Animated ASCII night city skyline
│   └── hologram.py                   # Animated 3D wireframe cube
├── install.sh                        # Symlink installer (Linux/WSL2)
├── install-mac.sh                    # Symlink installer (macOS)
└── README.md
```

## Setup

### macOS
```bash
git clone git@github.com:gitpancake/.dotfiles.git ~/dotfiles
cd ~/dotfiles
chmod +x install-mac.sh
./install-mac.sh
source ~/.zshrc
```

### Linux/WSL2
```bash
git clone git@github.com:gitpancake/.dotfiles.git ~/dotfiles
cd ~/dotfiles
chmod +x install.sh
./install.sh
source ~/.zshrc
```

## Zsh Theme

The `robbyrussell-bar` theme extends the default robbyrussell prompt with a full-width time separator:

```
── ──────────────────────────────────────────────────────────────── 14:30:25 ──
➜ my-project git:(main) ✗
```

## Tmux

Gruvbox dark theme with intuitive keybindings:

- `|` or `\` to split horizontally, `-` to split vertically
- `Alt+Arrow` to navigate panes, `Ctrl+Left/Right` to switch windows
- `Prefix + t` to set pane title, `Prefix + r` to rename window

Status bar shows system metrics with dynamic colors (green → yellow → orange → red):

```
 S  │  1:zsh   2:vim  │  BAT 85%  │  CPU 12%  │  MEM 43%  │  DSK 2%  │  14:30
```

Thresholds: 0-25% green, 26-50% yellow, 51-75% orange, 76-100% red. Battery is inverted (low = red).

## Claude Code: Cost Awareness

Three layers of friction keep heavy Opus usage from silently draining Max-plan usage buckets. Each catches what the others miss.

### Passive — Status line
`claude/statusline-command.sh` renders the Claude Code bottom status bar: a color-coded context-window bar, plus 5-hour and 7-day usage buckets that only appear once either crosses 50%. Consistent with the tmux status color scheme.

```
[████░░░░░░░░░░░░░░░░] 110k/1M 11%                             # quiet
[█████████████████░░░] 850k/1M 85% │ 5h 72% 1h 20m             # loud
```

### Reactive — Post-mortem tool
```bash
~/.claude/transcript-costs.sh [days=7] [top=10]
```
Ranks sessions by estimated API-equivalent cost, using Anthropic list prices per model. Surfaces which conversations actually burned budget and the first real prompt that started them.

### Preventive — CLAUDE.md rule + PostToolUse hook
The `Cost Discipline` section in `claude/CLAUDE.md` instructs Claude to propose the **batch pattern** (one LLM call produces a plan, a script applies it) before any N-item operation — avoiding per-item LLM calls at Opus prices.

Typical model selection:
- **Opus** — project planning, architecture, ambiguous work
- **Sonnet** — coding (default), reviews, most reasoning
- **Haiku** — mechanical edits, renames, simple greps

`claude/hooks/tool-loop-warn.sh` is a PostToolUse hook that fires a one-time warning per session when the same tool has been called ≥30× or total tool calls cross 100, suggesting the batch pattern or `/clear` between logical chunks.

## Focus Guard

Time-aware site blocker that swaps `/etc/hosts` and serves a status page for blocked domains on both HTTP and HTTPS.

**Focus windows:** Mon–Fri 09:00–18:00, Sat–Sun 11:00–15:00. Outside those hours, sites are unblocked automatically.

**How it works:** nginx runs persistently on ports 80 + 443. `/etc/hosts` redirects blocked domains to `127.0.0.1`, so every request lands on nginx and gets the status page instead of a browser error. A mkcert-issued cert (trusted via macOS Keychain) means HTTPS sites show the page cleanly with no certificate warning.

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

## Dependencies

- [Oh My Zsh](https://ohmyz.sh/)
- [nvm](https://github.com/nvm-sh/nvm)
- [Homebrew (Linuxbrew)](https://brew.sh/)
- [Claude Code](https://claude.ai/code)
- [jq](https://jqlang.org/) — required by `statusline-command.sh`, `transcript-costs.sh`, and `tool-loop-warn.sh`
