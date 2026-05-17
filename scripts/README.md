# scripts

User-facing helpers + terminal toys. Most are on `PATH` via `~/.dotfiles/scripts` exported in `.zshenv`.

## Files

| Script | What it does |
| --- | --- |
| `tickets-tui.py` | `tix` — terminal ticket explorer for `~/.claude/tickets/`. Split-pane preview, priority/status edits, pickup → `wt`. |
| `slack-tldr.py` | Socket-Mode daemon: subscribes to configured Slack channels, writes raw text alerts to a state file rendered by `slack-watch`. |
| `slack-tldr-pane.sh` | Static (passive) renderer for the alert state. `watch -tcn2 ~/.dotfiles/scripts/slack-tldr-pane.sh`. |
| `git-watch.py` | Lightweight git HEAD watcher. Writes commit feed state. Lighter cousin of `commit-watcher.py`. |
| `commit-watcher.py` | Watches a git remote, computes palette/intensity from changed paths + LOC delta, writes shared state for reactive art renderers. |
| `audio-watcher.py` | Audio-event watcher daemon. Configurable. |
| `claude_oauth.py` | Claude Code OAuth → Anthropic API helper. Reads tokens from the macOS keychain. |
| `redact_chatlogs.py` | Regex secret redactor for `~/.claude/projects/` transcripts. Run before sharing. |
| `watch.py` | Generic file-change watcher. |
| `city.py` | Animated ASCII night-city skyline. |
| `hologram.py` | Rotating 3D wireframe cube with holographic effects. |

## Slack alerts → tmux pane

Daemon subscribes to Slack channels via Socket Mode, captures each message's raw text (flattened, truncated), writes the result to a state file rendered in a tmux pane.

**Setup (one-time):**

1. Create a Slack app at <https://api.slack.com/apps> → *From scratch*.
2. **Socket Mode** → enable → generate App-Level Token (`xapp-…`) with scope `connections:write`.
3. **OAuth & Permissions** → Bot Token Scopes: `channels:history`, `groups:history`, `im:history`, `mpim:history`, `channels:read`, `users:read`, `usergroups:read`.
4. **Event Subscriptions** → enable → subscribe bot to `message.channels` (+ `message.groups` / `message.im` if private channels / DMs).
5. *Install to Workspace* → copy Bot Token (`xoxb-…`).
6. `cp scripts/slack-tldr.config.example.json scripts/slack-tldr.config.local` — fill in tokens and the `channels` dict (maps channel names → IDs, split into `alerts` and `monitor` tabs).
7. `/invite @your-bot` in each configured channel. Daemon verifies membership on startup and exits with an error if the bot is missing.
8. Re-run `./install-mac.sh` (or `./rewire-symlinks.sh`) to load the launchd agent.

**Live pane** (interactive — `q`/Ctrl-C exits, any key acks blinking alerts):

```bash
slack-watch
```

**Passive pane:**

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

## Reactive matrix (commit-driven art installation)

`commit-watcher.py` is the driver. Polls a remote, computes palette from changed file paths and LOC delta → intensity, optionally calls the Anthropic API for a poetic 1-line description, writes shared state.

State file: `~/.local/share/art/state.json` (override via `ART_STATE_FILE`). Any compatible curses renderer can poll it for coordinated animation across panes.

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

On boot, replays commits from the last `backfill_minutes` (default 30) oldest→newest with `backfill_stagger_ms` delay between each, so panes show a ripple of recent history immediately. Empty window → seeds from `HEAD`.

Config:

```bash
cp scripts/commit-watcher.config.example.json scripts/commit-watcher.config.local
$EDITOR scripts/commit-watcher.config.local        # set repo_path + rules
python3 scripts/commit-watcher.py                  # foreground
# or background:
nohup python3 scripts/commit-watcher.py >/tmp/watcher.log 2>&1 &
```

LLM describer: set `describer_enabled: true` and export `ANTHROPIC_API_KEY`. Descriptions cached by sha at `~/.local/share/art/describer-cache/<sha>.txt`.

**Manually trigger a burst (testing):**

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

## Audio watcher

`audio-watcher.py` is a daemon that watches for audio events. See `audio-watcher.config.example.json` for setup.

## Secret redaction

`redact_chatlogs.py` scrubs `~/.claude/projects/` transcripts of common secret patterns (Anthropic / OpenAI / GitHub / Slack / AWS / Google / Stripe / Sendgrid / Twilio / JWTs / PEM / SSH private keys / DB URLs / bearer tokens / `KEY=value` env). In-place, regex-based. Run before sharing a transcript.

## Terminal toys

```bash
python3 scripts/city.py
python3 scripts/hologram.py
```

`q` / Ctrl-C to exit.
