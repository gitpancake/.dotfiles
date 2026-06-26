# scripts

User-facing helpers + terminal toys. Most are on `PATH` via `~/.dotfiles/scripts` exported in `.zshenv`.

## Files

| Script | What it does |
| --- | --- |
| _(tix moved out)_ | `tix` now ships from github.com/gitpancake/tix — install with `pipx install tix-cli`. It's a pure reader; `status:` is a hand-driven field (`ticket-status-sync.py` was sunset 2026-06-16). |
| `slack-tldr.py` | Socket-Mode daemon: subscribes to configured Slack channels, writes raw text alerts to a state file rendered by `slack-watch`. |
| `slack-tldr-pane.sh` | Static (passive) renderer for the alert state. `watch -tcn2 ~/.dotfiles/scripts/slack-tldr-pane.sh`. |
| `git-watch.py` | Lightweight git HEAD watcher. Writes commit feed state. Lighter cousin of `commit-watcher.py`. |
| `commit-watcher.py` | Watches a git remote, computes palette/intensity from changed paths + LOC delta, writes shared state for reactive art renderers. |
| `audio-watcher.py` | Audio-event watcher daemon. Configurable. |
| `redact_chatlogs.py` | Regex secret redactor for `~/.claude/projects/` transcripts. Run before sharing. |
| `granola-tix-review.py` | Pull today's Granola transcripts → Opus reviews them against `~/.claude/tickets/` → interactive prompt to accept/skip new tickets, edits, redundancy calls. Learns from past decisions. |
| `linear-ticket.py` | Linear GraphQL client — replaces the Linear MCP so lanes never load its tool schemas. `create` → make an issue, print `identifier<TAB>url` (used by `/ship` §2.5 + bugfinder). `comment --id AE-NNNN` → post a comment (agents). Key from `$LINEAR_API_KEY` or `scripts/linear-ticket.config.local` (gitignored). |
| `watch.py` | Generic file-change watcher. |
| `city.py` | Animated ASCII night-city skyline. |
| `hologram.py` | Rotating 3D wireframe cube with holographic effects. |
| `ourman.py` | Ourman-inspired 140 BPM deep-dubstep bass visualizer: a throbbing sub-bass orb pulses on the beat, radiating bass rings under an oriental lattice over a tribal-rhythm spectrum. `q`/ESC quits. |

## ASCII art toys

Launched via the `art` zsh function (defined in `zsh/.zshrc`): `art <name>` runs `~/.local/share/art/<name>.py`, defaulting to `hologram` with no args. Current toys: `art hologram`, `art city`, `art ourman` (plus `art watch` for the reactive matrix).

**Adding a toy is two steps** — the launcher resolves names from `~/.local/share/art/`, *not* from this `scripts/` dir, and that directory is **hand-managed** (no installer or `rewire-symlinks.sh` touches it):

1. Drop `scripts/<name>.py` here.
2. `ln -sf ~/.dotfiles/scripts/<name>.py ~/.local/share/art/<name>.py`

Skip step 2 and `art <name>` prints `Unknown art: <name>` — the script exists but the dispatcher can't see it.

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

## Granola → tix review

`granola-tix-review.py` fetches today's Granola docs + transcripts, indexes `~/.claude/tickets/`, and asks Opus (via the Claude Code OAuth login) to suggest new tickets, edits, or redundancy calls. Each suggestion is reviewed interactively (`a`/`s`/`e`/`q`).

**Requires:** Granola desktop installed + signed in (uses `~/Library/Application Support/Granola/supabase.json` for auth), `claude` CLI logged in.

```bash
python3 scripts/granola-tix-review.py            # full run, interactive (today only)
python3 scripts/granola-tix-review.py --history 7  # last 7 days
python3 scripts/granola-tix-review.py --dry-run  # print suggestions only
python3 scripts/granola-tix-review.py --model claude-haiku-4-5-20251001  # cheaper
python3 scripts/granola-tix-review.py --cache ~/.granola-tix/last-suggestions.json  # replay last
```

**State** lives at `~/.granola-tix/` (outside the dotfiles repo, never committed):

- `feedback.md` — append-only decision log. Every accept/skip lands here with optional notes.
- `style.md` — distilled preference doc. Regenerated by Haiku after each run from `feedback.md`. Loaded into the next run's prompt so suggestions track your taste over time.
- `runs/<utc>.jsonl` — full suggestion + decision record per run.
- `last-prompt.md`, `last-suggestions.json` — debugging artifacts.

The token refresh uses the WorkOS refresh token stored by Granola; access tokens live ~6h and are minted in-memory per run. Nothing is written back to Granola's state.

## Terminal toys

```bash
python3 scripts/city.py
python3 scripts/hologram.py
```

`q` / Ctrl-C to exit.
