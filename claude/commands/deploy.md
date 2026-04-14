# Deploy / Ship Skill

Use when preparing to deploy, push to remote, or ship a feature to production.

## When This Activates
When asked to deploy, push, ship, or when a feature branch is ready to merge.

## Pre-Deploy Checklist

### 1. Verify the Code
- Run the test suite: `npm test`, `npx nx run-many --target=test --all -- --run`, or project-specific command.
- Run the build: `npm run build`. A passing build is mandatory.
- Run type checking if available: `npm run typecheck` or `npx tsc --noEmit`.
- Check for lint errors: `npm run lint`.

### 2. Verify the Branch
- `git status` — no untracked files that should be committed, no uncommitted changes.
- `git log --oneline -5` — commits are logical, messages are clear.
- If on a feature branch: verify it's up to date with main (`git fetch && git log main..HEAD`).

### 3. Verify the Diff
- `git diff main...HEAD` — review the full diff against main.
- No debug code, no commented-out blocks, no TODO hacks.
- No secrets, no .env files, no hardcoded credentials.

### 4. Deploy
- **Railway projects**: Push triggers auto-deploy. Watch paths determine which services rebuild.
- **Confirm before pushing**: Always confirm with the user before `git push`.
- **Never force push to main**.

## Post-Deploy
- Check health endpoints: `/health` should return 200.
- Check metrics if available: Prometheus at `:9090/metrics`.
- Watch logs for errors in the first few minutes.

## Principle
Measure twice, cut once. Every deploy is a potential rollback. Verify before you ship.
