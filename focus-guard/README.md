# focus-guard

Time-aware website blocker for macOS. Swaps `/etc/hosts` between a "blocked" and "open" state on a launchd-driven schedule, with a local nginx server rendering an HTTPS-valid status page when blocked sites are visited.

## How it works

1. **`focus-guard.sh`** runs every 10 minutes via launchd. It checks the current time of day and, if inside focus hours, symlinks `/etc/hosts` → `hosts.blocked`. Outside focus hours, it swaps to `hosts.open`.
2. **`focus.conf`** is loaded by nginx and serves a status page on ports 80 and 443 for every blocked domain — so the user sees a "you're focusing" page instead of a browser error.
3. **`cert-gen.sh`** generates an `mkcert` cert covering all blocked domains so HTTPS doesn't break. Regenerates only when the domain list changes.
4. **launchd plists** keep both the schedule (`focus-guard`) and the nginx process (`focus-nginx`) alive.

## Files

| File | Purpose |
| --- | --- |
| `focus-guard.sh` | Main scheduler — flips `/etc/hosts`, writes status HTML, regenerates cert if needed. |
| `cert-gen.sh` | mkcert wrapper that builds a SAN cert from the blocked-domain list. |
| `focus.conf` | nginx config: server blocks for ports 80 + 443, returns the status page for all blocked hosts. |
| `block` | Manual override — engage block immediately (until next scheduled run). |
| `unblock` | Manual override — release block for ~10 min (until next scheduled run). |
| `hosts.blocked.example` | Template for `/etc/hosts.blocked` — copy to your real path and add your domains. **Not committed with real domains.** |
| `com.henrypye.focus-guard.plist` | launchd job: runs `focus-guard.sh` every 10 minutes. |
| `com.henrypye.focus-nginx.plist` | launchd job: keeps nginx alive on ports 80 + 443. |

## Setup

1. Install dependencies: `brew install nginx mkcert nss`.
2. Run `mkcert -install` once to add the local CA to your system trust store.
3. Copy `hosts.blocked.example` to `/etc/hosts.blocked` and add your domains.
4. Symlink the launchd plists into `~/Library/LaunchAgents/` and `launchctl load` them.
5. Verify: `block` then visit a blocked domain — you should see the status page over HTTPS without a cert warning.

## Manual control

```bash
block     # block now
unblock   # unblock until next scheduled run (~10 min)
```

Both require sudo (they call `switch-hosts.sh` which writes `/etc/hosts`).

## Why this exists

Browser extensions can be disabled in 2 clicks. `/etc/hosts` is OS-level, requires sudo to edit, and survives Incognito mode and every browser. The added nginx layer turns the dead-end browser error into something more like a soft nudge.
