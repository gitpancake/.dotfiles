---
description: Triage missing Axiom dashboard instrumentation before dashboard creation
argument-hint: "[desired dashboard]"
---

# Axiom Dashboard Triage — instrument the gap, then build

Sibling to `/axiom-dashboard`. That command builds a dashboard from data that
**already exists** in Axiom. This one runs first when the data **does not exist
yet**: it takes a desired dashboard in free text, finds where the app would need
to emit the missing stats, proposes the code changes, offers to make them, and
opens a PR. Then it hands off to `/axiom-dashboard` to build the panels.

**Desired dashboard (free text):** `$ARGUMENTS`

Example: `I want an axiom dashboard that shows me all slack messages and teams
messages for Sundays`. The data path "messages by channel" is **not instrumented
today** (`channel` is empty in live data) — so this command closes that gap.

---

## Step 0 — Load credentials (same as `/axiom-dashboard`)

```bash
ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
ENVFILE=""
[ -f .env.local ] && ENVFILE=".env.local"
[ -z "$ENVFILE" ] && [ -n "$ROOT" ] && [ -f "$ROOT/.env.local" ] && ENVFILE="$ROOT/.env.local"
[ -z "$ENVFILE" ] && for d in "$ROOT"/../../.. "$HOME/Documents/code/cartage-agent"; do
  [ -f "$d/.env.local" ] && ENVFILE="$d/.env.local" && break
done
set -a; [ -n "$ENVFILE" ] && . "$ENVFILE"; set +a
: "${AXIOM_TOKEN:?AXIOM_TOKEN missing — add a dashboard-write PAT to .env.local}"
: "${AXIOM_DATASET:=REDACTED-DATASET-NAME}"
echo "envfile=${ENVFILE:-NONE} dataset=$AXIOM_DATASET token=set(${#AXIOM_TOKEN} chars)"
```

The token is only needed for the **verification dry-runs** (Step 2) and the final
handoff to `/axiom-dashboard`. Code-only triage works without it, but confirm it
loads early so the run doesn't dead-end at the dashboard step.

---

## Step 1 — Parse the desired dashboard into concrete signals

Restate `$ARGUMENTS` as a list of **panels**, each with the **field(s) it needs**.
Separate three kinds of clause — they are handled in different places:

| Clause kind            | Example                                          | Handled where                                                       |
| ---------------------- | ------------------------------------------------ | ------------------------------------------------------------------- |
| **Metric / breakdown** | "slack messages", "teams messages", "by channel" | needs a **field** in the data → code instrumentation (this command) |
| **Time window**        | "last 7d"                                        | dashboard `timeWindow*` (`/axiom-dashboard`)                        |
| **Recurrence**         | "for Sundays"                                    | dashboard APL `where dayofweek(_time) == 0d` — **NOT code**         |

So "all slack + teams messages for Sundays" decomposes to: a `channel` field
(slack / teams) — **instrumentation** — filtered by a Sunday day-of-week clause —
**dashboard-side**, no code. Only the field is a code gap.

Ask the user **one question at a time** only for genuine ambiguity (which channels
count, whether they want per-message or per-thread granularity). Do not batch.

---

## Step 2 — Gap analysis: does the data already exist?

For each needed field, check live Axiom **before** proposing any code. A field that
already flows needs no instrumentation — go straight to `/axiom-dashboard`.

1. **Is the field populated?** Dry-run via Pi's `axiom` tool (`action='apl'`) (rate-limited —
   sequential), tight time bound:
    ```apl
    ['REDACTED-DATASET-NAME'] | where _time > ago(7d) | where isnotempty(channel) | summarize n = count() by channel
    ```

    - Rows back → field exists; **skip instrumentation** for it.
    - Zero rows → gap confirmed (e.g. `channel` today). Check the nested path too —
      the field may exist under `data.*` but not promoted:
      `... | where isnotempty(['data.channel']) | summarize count() by ['data.channel']`.
2. **Record the verdict per field**: `exists top-level` / `exists under data.*` /
   `missing entirely`. This drives the change in Step 4 (promote vs add-and-promote).

---

## Step 3 — Locate the instrumentation sites in code (verified primitives)

The logging stack — confirmed real symbols, do not invent variants:

- **Logger:** default export of `src/utils/logger.utils.ts`. Methods:
  `logging.info(message, data?)`, `.warning`, `.error`, `.debug`, `.logXErr(params)`.
  `message` is a string; `data` is an object. Every call runs through
  `enrichWithRequestContext()`.
- **Field promotion:** `enrichWithRequestContext()` promotes any key in the
  `TOP_LEVEL_FIELDS` Set (in `logger.utils.ts`, ~line 376) to a **top-level**
  Axiom column; everything else nests under `data.*`. Current set:
  `requestId runId triggerRunId orgId userId workflowName threadId level message
stack timestamp`. **`channel` is NOT in it.**
- **Per-request context:** `src/utils/requestContext.utils.ts` — AsyncLocalStorage.
  `RequestContext` interface, `runWithRequestContextAsync()`, and
  `setRequestContextValue(key, value)` to set a field once so every log in that
  context inherits it.
- **Axiom transport:** `@axiomhq/winston` WinstonTransport, instantiated in
  `logger.utils.ts` only when `isProduction && AXIOM_TOKEN && AXIOM_DATASET`.
  Flushed per-log via `scheduleFlush()` and at task end via `withTaskContext`'s
  `finally` → `flushObservability()`.

**Find the emit sites** for the desired signal. For the messaging example:

- Slack: `src/trigger/handleSlackEvent.trigger.ts` — success log
  `logging.info("Inbound Slack message processed successfully", { code: "SLACK_MESSAGE_PROCESSED" })`
  and the `onFailure` log. Channel value is available on the payload (`event.channel`)
  but not logged.
- Teams: `src/trigger/handleTeamsEvent.trigger.ts` — success log
  `logging.info("Inbound Teams event processed successfully", { code: "TEAMS_EVENT_PROCESSED", ...extractActivityContext(...) })`.
- Starting-workflow logs: `handleSlackMessageEventWorkflow` / `handleTeamsEventWorkflow`
  (`logging.info("Starting …")`, no structured data).

**Pattern to copy (rich structured emit):**
`src/server/workflows/dispatchPipedreamEventWorkflow/utils/pipedreamContext.utils.ts`
— `emitIngestLatencyMetric` / `emitMapperLatencyMetric`: semantic message name +
data object with the metric name repeated, numeric/string values, optional fields
via conditional spread.

**Codebase rules that bite here:**

- The trigger files use `await import("@/utils/logger.utils")` **inside** the task.
  That dynamic import is sanctioned for Trigger.dev tasks (CLAUDE.md) — **keep the
  existing style**, do not "fix" it to a static import.
- camelCase, `XError` for throws, no silent catches, run Prettier on every edited
  file, `bun type-check` must pass.

---

## Step 4 — Propose the code changes (show diffs, do not apply yet)

Translate each gap into the **smallest** change that makes the field queryable.
Two shapes, pick per Step 2 verdict:

**A. Field missing entirely (e.g. `channel`) — recommended: promote + emit.**

1. Promote to a top-level column so dashboard APL is clean (`where channel == "slack"`
   instead of `tostring(['data.channel'])`):
    ```ts
    // src/utils/logger.utils.ts — TOP_LEVEL_FIELDS
    const TOP_LEVEL_FIELDS = new Set([
        "requestId",
        "runId",
        "triggerRunId",
        "orgId",
        "userId",
        "workflowName",
        "threadId",
        "channel",
        "level",
        "message",
        "stack",
        "timestamp",
    ])
    ```
2. Emit it at each handler's success **and** failure log:

    ```ts
    // src/trigger/handleSlackEvent.trigger.ts
    logging.info("Inbound Slack message processed successfully", {
        code: "SLACK_MESSAGE_PROCESSED",
        channel: "slack",
    })
    ```

    ```ts
    // src/trigger/handleTeamsEvent.trigger.ts
    logging.info("Inbound Teams event processed successfully", {
        code: "TEAMS_EVENT_PROCESSED",
        channel: "teams",
        ...extractActivityContext(payload.activity),
    })
    ```

    For per-thread granularity, also pass `threadId` (already top-level) from the
    payload (`event.thread_ts` / `conversationId`).

    **Alternative — set once via context** (cleaner when many logs in one flow need
    it): add `channel?: string` to `RequestContext`, then at the top of each handler
    `setRequestContextValue("channel", "slack")`. Every downstream log inherits it.
    Use this only if the dashboard needs channel on more than the one summary line.

**B. Field already under `data.*`, just not promoted.** Add it to `TOP_LEVEL_FIELDS`
only — no emit change. (Or leave it and have `/axiom-dashboard` query `['data.x']`.)

**Present to the user:**

- The gap table (field → verdict → proposed change), with the actual diffs.
- Which files change and why each.
- The note that **panels stay zero-rows until this ships and a deploy emits the
  field** — Axiom is not retroactive; historical events will never have `channel`.
- Then ask: **apply these changes?** Wait for confirmation.

---

## Step 5 — Apply, verify, and open the PR (only on confirmation)

1. **Branch via the lane command, not by hand.** This is feature work → use the
   project's standard. If already on a dedicated branch/worktree, stay; otherwise
   `feature/<slug>` (no numbers in slug).
2. Apply the edits. Run `npx prettier --write` on each changed file. Run
   `bun type-check` — must pass before proceeding.
3. **Create the Linear ticket** for the instrumentation (team: Autonomy Eng `AE-`
   for customer-facing observability, or Engineering). Title `Feature: …` with
   acceptance criteria ("`channel` populated for slack/teams; dashboard X renders").
4. **Open the PR with `/ship`** — never raw `gh pr create`. `/ship` composes the
   PR's Linear team-reference ticket from the real commits + diff and triggers
   review. Title `[AE-XXXX] - Instrument channel for messaging dashboard`.

---

## Step 6 — Hand off to `/axiom-dashboard`

The dashboard itself is the other command's job. Offer the user two paths:

- **Build now (zero-rows until deploy):** run `/axiom-dashboard <the original scope>`
  immediately. Panels are correct but empty until the instrumentation PR merges and
  deploys; good for having the dashboard ready and reviewable.
- **Build after deploy:** wait for the PR to merge + deploy, confirm the field is
  populated (re-run the Step 2 dry-run), then `/axiom-dashboard <scope>`.

Carry the resolved scope verbatim (including the recurrence clause, e.g. Sundays →
`where dayofweek(_time) == 0d`) so `/axiom-dashboard` doesn't re-ask.

---

## Out of scope

No alerts/monitors. No retroactive backfill (Axiom only sees events emitted after
deploy — say so explicitly). No name→orgId lookup (prompt, per `/axiom-dashboard`).
Does not build the dashboard itself — that is always `/axiom-dashboard`.
