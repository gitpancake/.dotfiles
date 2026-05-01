# scripts

Standalone terminal toys. Pure Python, `curses`-based, no dependencies beyond the stdlib.

## Files

| Script | What it does |
| --- | --- |
| `city.py` | Animated ASCII night city skyline — twinkling stars, lit windows. |
| `hologram.py` | Rotating 3D wireframe cube with holographic-style effects. |
| `matrix.py` | Falling green glyph rain — half-width katakana digital downpour. Reactive to a shared state file. |
| `commit-watcher.py` | Watches a git repo's main branch and writes the shared state file `matrix.py` reads. |

## Run

```bash
python3 scripts/city.py
python3 scripts/hologram.py
python3 scripts/matrix.py
```

Press `q` or `Ctrl+C` to exit.

## Reactive matrix (commit-driven art installation)

`matrix.py` polls `~/.local/share/art/state.json` (override via `ART_STATE_FILE`).
When present, palette / intensity / burst / scrolling message are applied live.
Every running `matrix.py` reading the same state stays in sync — drop one across
multiple tmux panes and they all wave together.

State schema:

```jsonc
{
  "sha": "abc123",
  "ts": 1735689600.0,        // commit unix ts
  "burst_ts": 1735689600.0,  // when last burst triggered (decays ~5s)
  "intensity": 1.4,          // 0.2-3.0, drives spawn + mutation rate
  "palette": "green",        // green | amber | magenta | cyan | red
  "message": "...",          // optional scrolling banner on bottom row
  "files_touched": ["..."],
  "recent": [{"sha": "...", "palette": "...", "subject": "..."}]
}
```

### commit-watcher

Driver process. Polls a remote, computes palette from changed file paths,
LOC delta → intensity, optionally calls the Anthropic API for a poetic
1-line description.

Config lives at `~/.dotfiles/scripts/commit-watcher.config.local`
(gitignored — copy `commit-watcher.config.example.json` and edit).

```bash
cp scripts/commit-watcher.config.example.json scripts/commit-watcher.config.local
$EDITOR scripts/commit-watcher.config.local        # set repo_path + rules
python3 scripts/commit-watcher.py                  # foreground
# or background it:
nohup python3 scripts/commit-watcher.py >/tmp/watcher.log 2>&1 &
```

LLM describer: set `describer_enabled: true` and export `ANTHROPIC_API_KEY`.
Descriptions are cached by sha at `~/.local/share/art/describer-cache/<sha>.txt`.

### Manually trigger a burst (testing)

```bash
python3 -c '
import json, time, os
p = os.path.expanduser("~/.local/share/art/state.json")
s = json.load(open(p)) if os.path.exists(p) else {}
s.update({"burst_ts": time.time(), "intensity": 2.5, "palette": "magenta",
          "message": "test burst"})
json.dump(s, open(p, "w"), indent=2)
'
```

Every `matrix.py` instance picks it up within ~0.5s.
