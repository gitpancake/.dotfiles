# tmux

tmux configuration with intuitive keybindings, gruvbox dark theme, and a system-stats status bar.

## Files

| File | Purpose |
| --- | --- |
| `.tmux.conf` | Main config: pane splits (`\|` / `-`), pane navigation (Alt+Arrow), tab navigation (Ctrl+Left/Right), pane border titles showing git branch per pane, gruvbox color scheme. |
| `tmux-status.sh` | Right-side status renderer. Shows BAT / CPU / MEM / DSK with dynamic color thresholds. Runs every `status-interval` (5s). |

## Color thresholds

System metrics use severity coloring (higher = worse):

| Range | Color |
| --- | --- |
| 0–25% | green |
| 26–50% | yellow |
| 51–75% | orange |
| 76–100% | red |

Battery is **inverted** (higher = better).

## Install

The installer symlinks both files:

```
~/.tmux.conf            → dotfiles/tmux/.tmux.conf
~/.tmux/tmux-status.sh  → dotfiles/tmux/tmux-status.sh
```

`.tmux.conf` invokes the status script from `~/.tmux/tmux-status.sh`.

## Editing

Keep `tmux-status.sh` fast — it runs every 5 seconds. Reload config without restarting tmux: `tmux source-file ~/.tmux.conf`.
