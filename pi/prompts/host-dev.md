---
description: Spin up or wake a hosted GCP dev environment for this branch.
---

# /host-dev

Spin up or wake a remote dev environment on GCP. No arguments needed.

Be directive, not inquisitive. Never ask technical questions — just execute.

## Steps

1. Check gcloud is authenticated:

```bash
gcloud auth list
```

2. Make scripts executable:

```bash
chmod +x scripts/dev-env.sh scripts/dev-env-provision.sh
```

3. Detect the current git branch from the current working directory. Do not `cd` elsewhere:

```bash
git rev-parse --abbrev-ref HEAD
```

If running inside a worktree, this returns the worktree's branch, not the main repo's branch.

4. Run the up command with the detected branch:

```bash
bash scripts/dev-env.sh up --branch <detected branch>
```

The script handles everything automatically:

- No VM exists → creates and provisions from scratch
- VM is stopped by idle auto-shutdown → starts it, refreshes tunnel URL
- VM is already running → prints the current tunnel URL

## After it is running

Print the following, replacing `<URL>` with the actual tunnel URL. Use this exact format:

```text
Your dev environment is live:

  <URL>

To develop on the VM, open another terminal and run:

  bun run dev-env ssh && cd ~/cartage-agent

Then you can:

  pi              # use Pi to write and edit code
  bun run test    # run tests
  git push        # push changes

Any file changes on the VM are reflected at the URL in real time via hot reload.
The URL is stable across restarts. The VM auto-shuts down after 24h idle — just run /host-dev again to wake it.

Slack events are blocked by default. To enable Wilson for a specific Slack channel:

  bun run dev-env slack-channel <CHANNEL_ID>

Get the channel ID from Slack: right-click channel name → View channel details → copy ID at the bottom.
This filters Hookdeck so only events from that channel reach your dev env, preventing duplicate responses.

You can use this Pi session to ask questions about the hosted environment, read VM logs, or troubleshoot issues.
```

Only print troubleshooting info if something actually went wrong during provisioning. Do not print troubleshooting steps on success.
