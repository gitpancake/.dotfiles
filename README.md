# Dotfiles

Personal dotfiles for WSL2 (Ubuntu) development environment.

## What's Included

```
dotfiles/
├── zsh/
│   ├── .zshrc                       # Zsh config (Oh My Zsh, nvm, brew, aliases)
│   └── robbyrussell-bar.zsh-theme   # Custom theme with battery/time status bar
├── claude/
│   ├── settings.json                # Claude Code settings and plugins
│   └── statusline-command.sh        # Status line showing battery, CPU, memory,
│                                    #   disk, git branch, node version, session time
├── install.sh                       # Symlink installer
├── CLAUDE.md                        # Instructions for Claude Code AI assistant
└── README.md
```

## Setup

```bash
git clone git@gitlab.com:gitpancake/dotfiles.git ~/dotfiles
cd ~/dotfiles
chmod +x install.sh
./install.sh
source ~/.zshrc
```

## Zsh Theme

The `robbyrussell-bar` theme extends the default robbyrussell prompt with a full-width status bar:

```
── 🔋 99% (Plugged in) ───────────────────────────────────────────── 14:30:25 ──
➜ my-project git:(main) ✗
```

Battery is color-coded: green (>50%), yellow (20-50%), red (<20%).

## Claude Code Status Line

Shows system info at the bottom of Claude Code sessions:

```
🔋99%⚡ │ CPU 5% │ MEM 14% │ DSK 2% │ ⎇ main │ ⬢ v24.14.0 │ ⏱ 23m │ 11:54:09
```

## Dependencies

- [Oh My Zsh](https://ohmyz.sh/)
- [nvm](https://github.com/nvm-sh/nvm)
- [Homebrew (Linuxbrew)](https://brew.sh/)
- [Claude Code](https://claude.ai/code)
