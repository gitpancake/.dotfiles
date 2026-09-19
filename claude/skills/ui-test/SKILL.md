---
name: ui-test
description: Drive the Cartage desktop app in headless Chromium on a hosted dev VM to produce manual-testing screenshots for a PR. Trigger: "ui test", "screenshot the feature", "manual test evidence", "playwright the app", "show me the UI for this PR", any request for browser-level proof that a UI change works.
---

# ui-test

A scenario is 10-20 lines against `scripts/cartageApp.ts`. It knows the app's cookie, deep links, readiness signals, and the evidence-branch push. Never hand-write a Playwright driver from scratch. Never start a local dev server: the app always runs on the branch's hosted VM.

## 1. Host the branch

Push, then `/host-dev` from the worktree. It prints the VM URL; the VM pulls every minute, so later pushes need nothing. That URL is `DEV_ENV_URL` below.

## 2. Write the scenario

Copy `scripts/scenario.example.ts` to the worktree root as `_uiTest.ts` (untracked, deleted afterwards, never committed). Edit the middle:

```ts
const app = await openCartageApp({ url, token, outDir })
await app.open("messages", { threadId })      // deep link, waits for the dock + the window
await app.waitForText("Slack")                // wait on content, never on time
await app.shot("01-messages-slack")
await app.open("mail", { threadId })
await app.open("settings"); await app.click("Config Tables")
await app.open("document", { docId })
await app.open("setup", { section: "integrations" })
await app.close()
```

Run it from the worktree root so `playwright` resolves from the repo:

```bash
DEV_ENV_URL=<vm-url> bun _uiTest.ts > ui-test.log 2>&1
```

Then read every PNG back with the Read tool. A screenshot is evidence only when it shows the change under test.

`app.page` is the raw Playwright page for anything the helpers don't cover.

### Deep-link contract (`useWindowManager.ts` → `parseWindowsFromUrl`)

`?w=<type>` opens a window; comma-separate for several. Params by type: `mail` → `threadId`; `document` → `docId`; `setup` → `section` or `cap`; `report` → `ref`; `template` → `kind=pdf&docType=…` or `kind=email&templateKey=…`; `explorer` → `path`. Types: setup, explorer, tables, reports, wilson, mail, messages, phone, tasks, warehouseScheduling (Docks), freightDashboard (Dashboard), cartagePay (Wallet), settings. The lib adds `restore=false` and drops the `desktop-store-<orgId>` localStorage entry before each `open`, so last session's windows never appear in a shot. Other localStorage keys (the active Wilson chat thread among them) survive.

## 3. Token

`mintToken({ userId, orgId })` shells to `generateDevEnvToken` (dev JWT secret from Secret Manager, 24h, valid on every VM). `sandboxIdentity()` reads `UI_TEST_ORG_ID` / `UI_TEST_USER_ID` from the environment or `~/.claude/.env` (the internal sandbox org). Another user: `bun run script -- findMyOrgId --email <email>`. A Cartage team member's token unlocks the admin UI regardless of role.

## 4. Evidence

Images never enter the PR diff (REVIEW.md 🔴). `pushEvidence({ ticket, prNumber, dir })` builds a parentless `evidence/<ticket>-manual-test-screenshots` branch from the PNGs (suffixes `-v2`, `-v3` when the name is taken) and returns a markdown line per image. Put one numbered step per screenshot under **Manual testing steps** in the PR body, each saying what the reader should see, then:

```bash
gh pr edit <n> --body-file <file>
~/.claude/scripts/devin-review.sh gate <pr-url>
```

## Gotchas the lib does not absorb

- A fresh VM compiles `/` for a minute or two on first hit. `open()` waits up to 180s for the dock; that is the compile, not a hang.
- A `/api/auth/userinfo` 401 fires on load. Cosmetic.
- Several hidden `<input type=file>` exist at once; `app.page.locator("input[type=file]").last()` was the one a dialog used.
- Every VM shares the dev Firestore. Anything the scenario creates is real for everyone on dev.
- Raw `app.page.getBy…` locators need `.first()`: an invisible duplicate composer persists across window switches and trips strict mode. The lib's `waitForText` / `click` already do this.
- `?w=mail&threadId=<id>` showed "No messages" for a thread whose `folder` and `isArchived` were both null (lane ENGH-1629, 2026-09-18). Open Mail and click into the thread until that is understood.
