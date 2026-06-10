# Dotfiles

Personal dotfiles for macOS and WSL2 (Ubuntu). Symlinked into `$HOME` by `install-mac.sh` / `install.sh`. Editing files in this repo updates the live config — no rebuild step.

## Setup

### macOS

```bash
git clone git@github.com:gitpancake/.dotfiles.git ~/.dotfiles
cd ~/.dotfiles
chmod +x install-mac.sh
./install-mac.sh
source ~/.zshrc
```

### Linux / WSL2

```bash
git clone git@github.com:gitpancake/.dotfiles.git ~/.dotfiles
cd ~/.dotfiles
chmod +x install.sh
./install.sh
source ~/.zshrc
```

After editing the installer or adding new symlink targets, run `./rewire-symlinks.sh` to re-apply links without a full reinstall.

## Structure

Each top-level folder has its own README with the deep dive — this tree is just the index.

```
.dotfiles/
├── zsh/                     # zsh config, theme            → zsh/README.md
├── tmux/                    # tmux config, status bar,
│                            #   parallel-lane agent board  → tmux/README.md
├── claude/                  # Claude Code: settings, hooks,
│                            #   agents, commands, skills,
│                            #   wt lanes, cost             → claude/README.md
├── pi/                      # Pi: settings, keybindings,
│                            #   extensions, prompts,
│                            #   skills, themes, bin        → pi/README.md
├── scripts/                 # Slack TLDR, git-watch,
│                            #   reactive art, redactor     → scripts/README.md
├── ghostty/                 # Ghostty config (Gruvbox Material Medium Dark)
├── iterm/                   # iTerm2 Gruvbox presets       → iterm/README.md
├── vim/                     # minimal .vimrc (gruvbox)     →  (file is the doc)
├── install-mac.sh           # macOS installer
├── install.sh               # Linux / WSL2 installer
├── rewire-symlinks.sh       # re-link without full reinstall
├── _link-dotfiles.sh        # symlink rules (sourced by installers)
└── CLAUDE.md                # project memory for Claude (this repo's gotchas)
```

## Cross-cutting concepts

**Symlinks, not copies.** Almost everything is `ln -sf`'d into `$HOME`. Edit the file in this repo, the change is live. Exception: the `claude/local.*.plist` files are *generated* into `~/Library/LaunchAgents/` with `DOTFILES_DIR_PLACEHOLDER` substituted — re-run `rewire-symlinks.sh` after editing those.

**Private state lives outside the repo.** `~/.claude/org/<org>/`, `~/.pi/agent/auth.json`, `~/.pi/agent/.env.local`, `~/.pi/agent/sessions/`, `~/.zshenv.local`, `scripts/*.config.local` — all gitignored or system-side only. `.gitignore` is the source of truth for what stays out.

**Lane workflow.** Parallel Claude lanes spawn via `wt <slug>` (claude/bin/wt). Each lane is fire-and-forget through to a PR. The `tmux/agent-board.sh` pane is the visible contract — one row per lane, color-coded by state. Full details in `claude/README.md`.

**Cost discipline.** Two layers (statusline, post-mortem `transcript-costs.sh`) keep heavy Opus usage from silently draining Max-plan buckets. See `claude/README.md`.

**Secret redaction.** `scripts/redact_chatlogs.py` scrubs `~/.claude/projects/` transcripts of common secret patterns. Run before sharing.

## Dependencies

- [Oh My Zsh](https://ohmyz.sh/), [nvm](https://github.com/nvm-sh/nvm), [Homebrew (Linuxbrew)](https://brew.sh/)
- [Claude Code](https://claude.ai/code)
- [jq](https://jqlang.org/) — required by statusline + cost + warn hooks
- [tmux](https://github.com/tmux/tmux), [zoxide](https://github.com/ajeetdsouza/zoxide), [fzf](https://github.com/junegunn/fzf), [glow](https://github.com/charmbracelet/glow)
- [`tix`](https://github.com/gitpancake/tix) — ticket explorer. `pipx install tix-cli`. `TIX_PRELOAD_HOOK` (set in `zsh/.zshenv`) points it at `claude/scripts/ticket-status-sync.py`.
- [`wt-lanes`](https://github.com/gitpancake/wt-lanes) — parallel-lane infrastructure. `git clone https://github.com/gitpancake/wt-lanes ~/.wt-lanes && ~/.wt-lanes/install.sh`. Provides `wt`, `wt-gc`, `agent-board`, lane hooks. `WT_TICKET_SYNC` (set in `zsh/.zshenv`) wires `wt` spawn → `ticket-status-sync.py`.
- Python 3 stdlib (`curses`) — terminal toys
