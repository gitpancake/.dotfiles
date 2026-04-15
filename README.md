# Dotfiles

Personal dotfiles for macOS and WSL2 (Ubuntu) development environments.

## What's Included

```
dotfiles/
├── zsh/
│   ├── .zshrc                       # Zsh config (Oh My Zsh, nvm, brew, aliases)
│   └── robbyrussell-bar.zsh-theme   # Custom theme with time separator bar
├── tmux/
│   ├── .tmux.conf                   # tmux config (keybindings, gruvbox dark theme)
│   └── tmux-status.sh               # Status bar: battery, CPU, memory, disk
│                                    #   with dynamic color-coded thresholds
├── claude/
│   ├── settings.json                # Claude Code settings and plugins
│   ├── CLAUDE.md                    # Global instructions for Claude Code AI
│   ├── commands/                    # Specialized agent profiles (/backend, /frontend, etc.)
│   └── hooks/                       # Event hooks (e.g. tmux bell on task completion)
├── scripts/
│   ├── city.py                      # Animated ASCII night city skyline
│   └── hologram.py                  # Animated 3D wireframe cube
├── install.sh                       # Symlink installer (Linux/WSL2)
├── install-mac.sh                   # Symlink installer (macOS)
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

## Dependencies

- [Oh My Zsh](https://ohmyz.sh/)
- [nvm](https://github.com/nvm-sh/nvm)
- [Homebrew (Linuxbrew)](https://brew.sh/)
- [Claude Code](https://claude.ai/code)
