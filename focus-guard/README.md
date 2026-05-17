# focus-guard

Time-aware website blocker for macOS. Swaps `/etc/hosts` between a "blocked"
and "open" state on a launchd-driven schedule, with a local nginx server
rendering an HTTPS-valid status page when blocked sites are visited.

## How it works

1. **`focus-guard.sh`** runs every 10 minutes as **root** via a LaunchDaemon
   (the `tick` path). It computes the target from the schedule (or an
   override file), then **atomically** writes `/etc/hosts` — `blocked` →
   `/etc/hosts.blocked`, `open` → a copy *derived from* `/etc/hosts.blocked`
   with the 127.0.0.1 block lines commented out. It then **verifies** the
   copy landed (`cmp`); on failure it retries once and, failing that, serves
   a distinct **degraded** page and exits non-zero so launchd surfaces it.
2. The swap is **enforced every tick** (self-heal) — only the log line is
   gated on a state change. Drift heals within one tick.
3. The served status page is **derived from the real `/etc/hosts`**, never
   from the assumed target. It says "Unblocked" *only* when `/etc/hosts` is
   byte-identical to the derived open file.
4. **`focus.conf`** is loaded by nginx (ports 80 + 443) and serves the status
   page for every blocked domain. `keepalive_timeout 0` is set server-wide so
   nginx sends `Connection: close` — without it Chromium pools a keep-alive
   socket and keeps hitting the block page after `/etc/hosts` opens.
5. **`focus-doctor.sh`** is a manual health check (see below).
6. **`cert-gen.sh`** builds an `mkcert` SAN cert for all blocked domains so
   HTTPS doesn't warn. Regenerates only when the domain list changes.

## Privilege model

`/etc/hosts` is `root:wheel 0644` — only root can rewrite it. The schedule
therefore runs as a **LaunchDaemon** in `/Library/LaunchDaemons/` (root), not
a LaunchAgent (logged-in user). A LaunchAgent is *architecturally unable* to
swap `/etc/hosts`, which is why a stale block could persist forever.

Daemons are loaded with the modern API:

```bash
sudo launchctl bootstrap system /Library/LaunchDaemons/local.focus-guard.plist
sudo launchctl bootstrap system /Library/LaunchDaemons/local.focus-nginx.plist
```

Legacy `launchctl load` is a silent no-op for system daemons on current
macOS — `install-mac.sh` / `rewire-symlinks.sh` use `bootstrap`/`bootout`.

`block` / `unblock` shell out to `sudo focus-guard.sh block|unblock` — the
single writer. (The old unvendored `/usr/local/bin/switch-hosts.sh` is no
longer used.)

## Derived open state

There is no hand-maintained `/etc/hosts.open`. focus-guard derives it from
`/etc/hosts.blocked` every tick by commenting out the active 127.0.0.1 block
lines (localhost/broadcasthost kept live) and refreshes `/etc/hosts.open`
from that. Open and blocked therefore cannot desync — the root cause of the
original "Unblocked page while still blocked" incident.

## Files

| File | Purpose |
| --- | --- |
| `focus-guard.sh` | Scheduler core: `tick`/`block`/`unblock`. Atomic swap, verify-or-degrade, self-heal, real-state-derived HTML. |
| `focus-doctor.sh` | Health check — daemons loaded, nginx up, hosts↔state, cert valid. |
| `cert-gen.sh` | mkcert wrapper that builds a SAN cert from the blocked-domain list. |
| `focus.conf` | nginx config: ports 80 + 443, server-wide `keepalive_timeout 0`. |
| `block` / `unblock` | Manual override → `sudo focus-guard.sh block|unblock`. |
| `hosts.blocked.example` | Template for `/etc/hosts.blocked`. **Not committed with real domains.** |
| `local.focus-guard.plist` | LaunchDaemon: `focus-guard.sh` every 10 min (root). |
| `local.focus-nginx.plist` | LaunchDaemon: keeps nginx alive on 80 + 443. |
| `test/*.test.sh` | Sandboxed bash test harnesses (no root/launchd/nginx). |

## Setup

focus-guard is opt-in — not part of the main dotfiles install. Install it on
its own:

```bash
./focus-guard/install.sh
```

That installs nginx/mkcert/nss via brew, runs `mkcert -install`, copies the
scripts to `/usr/local/bin`, wires the nginx config, and `bootstrap`s both
LaunchDaemons. Re-running it is a refresh — safe to invoke after editing the
source files in this repo.

After installing:

1. Edit `/etc/hosts.blocked` and add the domains you want blocked.
2. `sudo /usr/local/bin/cert-gen.sh && sudo /opt/homebrew/bin/nginx -s reload`.
3. `focus-doctor.sh` (all ✓), then `block` and visit a blocked domain —
   status page over HTTPS, no cert warning.

To remove:

```bash
./focus-guard/uninstall.sh
```

Tears down both LaunchDaemons, removes the scripts + nginx config + runtime
state, restores `/etc/hosts` to its open form (with a `.bak.focus-uninstall`
backup). Brew formulae (mkcert/nss/nginx) are left in place — remove
manually with `brew uninstall` if no longer needed.

## Manual control

```bash
block               # block now, persists until `unblock`
unblock             # clear override; re-apply schedule (~10 min granularity)
focus-doctor.sh     # health check (sudo for full daemon status)
```

`block`/`unblock` invoke `sudo` internally.

## Health check

```bash
sudo /usr/local/bin/focus-doctor.sh
```

Reports: both daemons loaded (and the exact `bootstrap` command if not),
nginx answering the sentinel probe, `/etc/hosts` ↔ state ↔ schedule
consistent, TLS cert valid. Exits non-zero on any failure, so it can feed a
statusline/tmux or a launchd alarm. `FG_DOCTOR_CERT_MIN_SECS=<n>` warns ahead
of cert expiry.

## Troubleshooting: site still blocked after unblock

`/etc/hosts` is open but the browser cached the old 127.0.0.1 mapping. The
status page detects this (probe sentinel) and, after a few hits, stops
silently re-trapping and shows actionable copy. To clear it:

- Chromium: visit `chrome://net-internals/#dns` → **Clear host cache**, then
  retry. Or fully quit and reopen the browser.
- Confirm the OS side is actually open: `sudo focus-doctor.sh` should report
  `/etc/hosts ↔ state consistent (open)`.
- If the doctor says daemons are NOT loaded, run the printed `bootstrap`
  command (this is the failure mode behind a permanently stuck page).

## Why this exists

Browser extensions are disabled in 2 clicks. `/etc/hosts` is OS-level,
requires sudo to edit, and survives Incognito and every browser. The nginx
layer turns the dead-end browser error into a soft nudge.
