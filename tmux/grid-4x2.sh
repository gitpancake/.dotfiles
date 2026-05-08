#!/usr/bin/env bash
# Pad current window to 8 panes and arrange them in a 4x2 grid.
# Bound to: prefix + l (see .tmux.conf).

set -e
trap 'tmux display-message "grid-4x2: failed at line $LINENO"' ERR

TARGET=8
NC=4
NR=2

win=$(tmux display-message -p '#{window_id}')
W=$(tmux display-message -p '#{window_width}')
H=$(tmux display-message -p '#{window_height}')
n=$(tmux display-message -p '#{window_panes}')

if [ "$n" -gt "$TARGET" ]; then
  tmux display-message "grid-4x2: $n panes already open (>8); aborting."
  exit 1
fi

while [ "$n" -lt "$TARGET" ]; do
  tmux split-window -t "$win" -c "#{pane_current_path}" >/dev/null
  n=$((n + 1))
done

# Normalize first so split-window pane sizes don't fail validation.
tmux select-layout -t "$win" tiled >/dev/null

pids=()
while IFS= read -r line; do
  pids+=("$line")
done < <(tmux list-panes -t "$win" -F '#{pane_index}')

layout=$(/usr/bin/env python3 - "$W" "$H" "$NC" "$NR" "${pids[@]}" <<'PY'
import sys

W, H, NC, NR = (int(x) for x in sys.argv[1:5])
pids = sys.argv[5:]

def split(total, n):
    base = (total - (n - 1)) // n
    extra = (total - (n - 1)) - base * n
    return [base + (1 if i < extra else 0) for i in range(n)]

cw = split(W, NC)
rh = split(H, NR)

def offsets(sizes):
    out = [0]
    for s in sizes[:-1]:
        out.append(out[-1] + s + 1)
    return out

xs = offsets(cw)
ys = offsets(rh)

rows = []
i = 0
for r in range(NR):
    cells = [f"{cw[c]}x{rh[r]},{xs[c]},{ys[r]},{pids[i+c]}" for c in range(NC)]
    rows.append(f"{W}x{rh[r]},0,{ys[r]}{{{','.join(cells)}}}")
    i += NC

body = f"{W}x{H},0,0[{','.join(rows)}]"

c = 0
for b in body.encode():
    c = ((c >> 1) + ((c & 1) << 15)) & 0xffff
    c = (c + b) & 0xffff
print(f"{c:04x},{body}")
PY
)

tmux select-layout -t "$win" "$layout" >/dev/null
