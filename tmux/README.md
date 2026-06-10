# tmux

tmux configuration with intuitive keybindings, gruvbox dark theme, system-stats status bar, and a parallel-lane agent board.

## Files

| File | Purpose |
| --- | --- |
| `.tmux.conf` | Main config: pane splits (`\|` / `-`), pane navigation (Alt+Arrow), tab navigation (Ctrl+Left/Right), pane border titles showing git branch per pane, gruvbox color scheme. |
| `tmux-status.sh` | Right-side status renderer. BAT / CPU / MEM / DSK with dynamic color thresholds. Runs every `status-interval` (5s). |
| `grid-6.sh` | 5-pane grid layout (3 columns, double-wide middle spanning full height). Bound to `prefix + l`. Idempotent: idle shell panes auto-launch `slack-watch`, the agent board, and `git-watch`; running watchers are never clobbered. |

## Color thresholds

System metrics use severity coloring (higher = worse):

| Range | Color |
| --- | --- |
| 0–25% | green |
| 26–50% | yellow |
| 51–75% | orange |
| 76–100% | red |

Battery is **inverted** (higher = better).

## Agent board (parallel lanes)

`agent-board.sh` is a single-pane status board for parallel worktree agents. Pin it:

```bash
watch -tcn2 ~/.tmux/agent-board.sh
```

One row per worktree, sorted by urgency, color-coded by state:

```
LANE                          STATE              AGE    CTX    PORT
----------------------------------------------------------------
example-1 harden webhook        ACTIVE:Bash        0s     231K   3116
example-2 skip modal no-input   W:ambiguity        4m     78K    3115
example-3 cleanup auth          DONE               12m    -      3104
```

- **STATE** — `ACTIVE`, `WAITING:<code>`, `RUNNING:precheck`, `FAILED:<step>`, `DONE`, `IDLE`. Codes in `claude/agent-state-vocab.md`.
- **AGE** — time since the lane last changed state.
- **CTX** — live context-window tokens parsed from `~/.claude/projects/<encoded>/*.jsonl`. Cached by jsonl mtime+size so 2s ticks stay cheap.
- **PORT** — per-lane dev-server port (`<wt>/.env.local.port`).

Stale `IDLE` rows hide after 30 min (`BOARD_HIDE_IDLE_AFTER` to override; `BOARD_SHOW_ALL=1` to disable). Liveness check reaps lanes whose `claude` PID is dead — board self-heals to `IDLE` so killed terminals don't pile up red.

Optional: `AGENT_BOARD_WINDOW_NAME=<name>` pins the surrounding tmux window's title. Unset → window name is left alone.

## Install

The installer symlinks:

```
~/.tmux.conf                → dotfiles/tmux/.tmux.conf
~/.tmux/tmux-status.sh      → dotfiles/tmux/tmux-status.sh
~/.tmux/grid-6.sh           → dotfiles/tmux/grid-6.sh
```

`~/.tmux/agent-board.sh` is owned by [wt-lanes](https://github.com/gitpancake/wt-lanes) — its installer symlinks it (see Agent board below).

`.tmux.conf` invokes the status script from `~/.tmux/tmux-status.sh`.

## Editing

Keep `tmux-status.sh` and `agent-board.sh` fast — both run on a short interval. Reload config: `tmux source-file ~/.tmux.conf`.
