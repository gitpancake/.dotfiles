#!/usr/bin/env bash
# Pad current window to 5 panes: a 3-column grid with a double-width
# middle column that spans the full height as a single pane. The left
# and right columns each split into a top and bottom pane.
# Bound to: prefix + l (see .tmux.conf).
#
#   +----+---------+----+
#   | 0  |         | 2  |
#   +----+    1    +----+
#   | 3  |         | 4  |
#   +----+---------+----+

set -e
trap 'tmux display-message "grid-6: failed at line $LINENO"' ERR

TARGET=5

win=$(tmux display-message -p '#{window_id}')
W=$(tmux display-message -p '#{window_width}')
H=$(tmux display-message -p '#{window_height}')
n=$(tmux display-message -p '#{window_panes}')

if [ "$n" -gt "$TARGET" ]; then
  tmux display-message "grid-6: $n panes already open (>$TARGET); aborting."
  exit 1
fi

# Normalize up front so the first split has room even if the current
# layout has slivers (e.g. a 1-row pane after manual resizes).
tmux select-layout -t "$win" tiled >/dev/null

while [ "$n" -lt "$TARGET" ]; do
  tmux split-window -t "$win" -c "#{pane_current_path}" >/dev/null
  # Re-tile every iteration so the next split always targets a viable pane.
  tmux select-layout -t "$win" tiled >/dev/null
  n=$((n + 1))
done

pids=()
while IFS= read -r line; do
  pids+=("$line")
done < <(tmux list-panes -t "$win" -F '#{pane_index}')

layout=$(/usr/bin/env python3 - "$W" "$H" "${pids[@]}" <<'PY'
import sys

W, H = int(sys.argv[1]), int(sys.argv[2])
pids = sys.argv[3:]

# Column weights: middle column is double-width.
weights = [1, 2, 1]

def split_weighted(total, weights):
    avail = total - (len(weights) - 1)  # reserve 1 col per separator
    unit = sum(weights)
    base = [avail * w // unit for w in weights]
    extra = avail - sum(base)
    for i in range(extra):
        base[i] += 1
    return base

def split_even(total, n):
    base = (total - (n - 1)) // n
    extra = (total - (n - 1)) - base * n
    return [base + (1 if i < extra else 0) for i in range(n)]

def offsets(sizes):
    out = [0]
    for s in sizes[:-1]:
        out.append(out[-1] + s + 1)
    return out

cw = split_weighted(W, weights)
rh = split_even(H, 2)
xs = offsets(cw)
ys = offsets(rh)

# Pane order: left-top, left-bottom, middle, right-top, right-bottom.
lt, lb, mid, rt, rb = pids

def column(w, x, top_pid, bot_pid):
    top = f"{w}x{rh[0]},{x},{ys[0]},{top_pid}"
    bot = f"{w}x{rh[1]},{x},{ys[1]},{bot_pid}"
    return f"{w}x{H},{x},0[{top},{bot}]"

left = column(cw[0], xs[0], lt, lb)
middle = f"{cw[1]}x{H},{xs[1]},0,{mid}"
right = column(cw[2], xs[2], rt, rb)

body = f"{W}x{H},0,0{{{left},{middle},{right}}}"

c = 0
for b in body.encode():
    c = ((c >> 1) + ((c & 1) << 15)) & 0xffff
    c = (c + b) & 0xffff
print(f"{c:04x},{body}")
PY
)

tmux select-layout -t "$win" "$layout" >/dev/null

# Launch watchers in their panes. Only fire when the pane is an idle
# shell so re-pressing prefix+l is idempotent (won't clobber a running
# watcher). Pane order: 1=left-top 2=left-bot 3=middle 4=right-top
# 5=right-bot (pane-base-index 1).
run_in_pane() {
  local idx=$1 cmd=$2 cur
  cur=$(tmux display-message -p -t "$win.$idx" '#{pane_current_command}')
  case "$cur" in
    zsh|-zsh|bash|-bash|sh|-sh|fish)
      tmux send-keys -t "$win.$idx" "$cmd" Enter ;;
  esac
}

run_in_pane 2 'slack-watch'
run_in_pane 4 'watch -tcn2 ~/.tmux/agent-board.sh'
run_in_pane 5 'git-watch'
