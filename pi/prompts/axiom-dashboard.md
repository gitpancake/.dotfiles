---
description: Create a verified Axiom dashboard from a free-text scope
argument-hint: "[scope]"
---

# Create an Axiom Dashboard

Turn a free-text scope into a verified Axiom dashboard, created via the REST API.
This kills the manual "build the panels in the Axiom UI / hand off to Pete" step
that `docs/runbooks/release-usage-dashboards.md` §6 and
`docs/runbooks/pipedream-observability.md` §4 both assume.

**Scope (free text):** `$ARGUMENTS`

Examples: `all Teams interactions for Sundays`, `messaging interactions org-wide`,
`Ryder + Unishippers usage for Moe's`, `Pipedream transport errors last 24h`.

---

## Step 0 — Load credentials from `.env.local`

```bash
# Worktrees usually have NO .env.local — fall back to the repo-root checkout.
ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
ENVFILE=""
[ -f .env.local ] && ENVFILE=".env.local"
[ -z "$ENVFILE" ] && [ -n "$ROOT" ] && [ -f "$ROOT/.env.local" ] && ENVFILE="$ROOT/.env.local"
# In a worktree, $ROOT points at the worktree; the real checkout is the parent repo:
[ -z "$ENVFILE" ] && for d in "$ROOT"/../../.. "$HOME/Documents/code/cartage-agent"; do
  [ -f "$d/.env.local" ] && ENVFILE="$d/.env.local" && break
done
set -a; [ -n "$ENVFILE" ] && . "$ENVFILE"; set +a
: "${AXIOM_TOKEN:?AXIOM_TOKEN missing — add a dashboard-write PAT to .env.local (see .env.local.example)}"
: "${AXIOM_DATASET:=REDACTED-DATASET-NAME}"   # default, not a hard stop
echo "envfile=${ENVFILE:-NONE} dataset=$AXIOM_DATASET token=set(${#AXIOM_TOKEN} chars)"
```

If `AXIOM_TOKEN` is unset everywhere, STOP and tell the user to add it to
`.env.local` (mirror `.env.local.example`). Never print the token value.
`AXIOM_DATASET` is **not** a hard stop — it defaults to `REDACTED-DATASET-NAME`.
(Verified 2026-05-20: the live token sits in the repo-root `.env.local`, not the
worktree; the dataset line was absent and the default carried it.)

> The ingest/MCP token and the dashboard-write PAT are different scopes. A
> read-only token loads fine here but 401s at Step 6. If Step 6 returns 401,
> the fix is a PAT with dashboard write — not a query change.

Region is **US** (`api.axiom.co`). If this org is ever moved to EU, swap the
host to `api.eu.axiom.co` in Step 6.

---

## Step 1 — Parse the scope, then ask for missing clarifiers (one at a time)

Read `$ARGUMENTS` and resolve these. Ask the user **one question at a time**;
do not batch. Do not proceed until each is answered.

1. **Org filter.**
    - Scope names a specific org (e.g. "Moe's", "Friant", "Sundays") →
      **ALWAYS prompt for the `orgId`.** There is no name→ID map in this command.
      Paste it verbatim into every panel's `where orgId == "<id>"`.
    - Scope says "org-wide" / "all orgs" / no org → **omit the `orgId` filter
      entirely.** Do not invent a placeholder.
2. **Time window.** Map to `timeWindowStart = "qr-now-<N><unit>"` (`timeWindowEnd`
   is always `"qr-now"`). `7d`/`24h`/`30d` etc. Default to `7d` only after asking.
    - A **recurrence** ("Sundays", "weekdays") is NOT a time window — it is an APL
      `where` clause (`where dayofweek(_time) == 0d` for Sunday). Keep the rolling
      window (ask its length) AND add the day-of-week filter to each panel's APL.
3. **What counts as "messaging"** (only if the scope says "messaging"). Confirm
   which top-level `channel` values count (e.g. `teams`, `slack`, `whatsapp`).
   Messaging interactions are keyed on top-level `channel` / `threadId`.
4. **Which metrics** (if the scope is vague). Offer the canonical panels for the
   matched domain (Step 3) and let the user trim.

---

## Step 2 — Dataset shape (reference)

`REDACTED-DATASET-NAME`, 30-day retention. Top-level indexed fields:

```
orgId userId channel threadId threadTs workflowName message level
requestId runId triggerRunId timestamp
```

Everything else is nested under the `data.*` object map (also `attributes.custom`,
`resource.custom`). **The runbooks' `fields.*` paths are stale** — the live
dataset nests under `data.*`. Use `['data.metric']`, `todouble(['data.durationMs'])`,
`tostring(['data.integration'])`, etc.

---

## Step 3 — Canonical APL library (source from the runbooks, do not reinvent)

For Teams / messaging / usage / Pipedream scopes, lift the queries below rather
than writing new ones. They come from
`docs/runbooks/release-usage-dashboards.md` and
`docs/runbooks/pipedream-observability.md`. Substitute `<id>` with the prompted
`orgId`, or drop the `where orgId` line entirely for org-wide. Drop the
`where _time` line — the dashboard's `timeWindow*` drives the range.

**Teams usage (verified live):**

```apl
['REDACTED-DATASET-NAME']
| where orgId == "<id>"
| where message == "Inbound Teams event processed successfully"
| summarize teamsEvents = count() by bin_auto(_time)
```

Broaden to include resolved-but-incomplete events:
`| where message startswith "handleTeamsEventWorkflow" or message == "Inbound Teams event processed successfully"`

**Messaging interactions (keyed on top-level `channel`):**

> ⚠ Verified 2026-05-20: top-level `channel` is **empty in live data** (0 rows /
> 7d over 6.3M events). A `channel`-keyed dashboard renders all-zero today. If the
> scope is "all messages flowing through the system", confirm with the user — they
> usually mean the **app-log `message` stream** (see panel set below), not the
> messaging substrate. Only use the `channel` queries once that field starts
> flowing.

```apl
['REDACTED-DATASET-NAME']
| where isnotempty(channel)
| where channel in ("teams", "slack", "whatsapp")   // trim to the confirmed set
| summarize interactions = count() by channel, bin_auto(_time)
```

**System log-message stream (verified live — the usual "all messages" reading):**
The dataset mixes app-log events (top-level `message`/`level`/`orgId`/
`workflowName`/`requestId`) with Trigger.dev OTel spans (those have `message`/
`channel` null). `isnotempty(message)` isolates app logs (~628k / 7d, `level` ∈
`info`/`error`/`warning`). Canonical org-wide panel set:

```apl
# total volume (Statistic)
['REDACTED-DATASET-NAME'] | where isnotempty(message) | summarize ['Total Messages'] = count()
# error rate % (Statistic)
['REDACTED-DATASET-NAME'] | where isnotempty(message)
| summarize total = count(), errors = countif(level == "error")
| extend ['Error Rate %'] = round(todouble(errors) / todouble(total) * 100, 2) | project ['Error Rate %']
# volume by level (TimeSeries)
['REDACTED-DATASET-NAME'] | where isnotempty(message) | summarize count() by level, bin_auto(_time)
# top messages / top error messages (Table)
['REDACTED-DATASET-NAME'] | where isnotempty(message) | summarize count = count() by message | order by count desc | take 20
# recent errors (Table — see Step 5: no LogStream type exists)
['REDACTED-DATASET-NAME'] | where level == "error" | project-keep _time, message, workflowName, orgId, requestId | order by _time desc | take 100
```

**Ryder API usage (success vs error):**

```apl
['REDACTED-DATASET-NAME']
| where orgId == "<id>"
| where message contains "RyderService."
| extend outcome = case(
    message contains ": Error", "error",
    message endswith ": response", "success",
    message endswith ": request", "request",
    "other")
| where outcome in ("success", "error")
| summarize count() by outcome, bin_auto(_time)
```

Per-method volume:

```apl
['REDACTED-DATASET-NAME']
| where orgId == "<id>"
| where message startswith "RyderService." and message endswith ": request"
| extend method = extract("RyderService\\.([a-zA-Z]+)", 1, message)
| summarize count() by method, bin_auto(_time)
```

**Shopify usage (works against historical data):**

```apl
['REDACTED-DATASET-NAME']
| where orgId == "<id>"
| where message startswith "integrations.feed."
    and tostring(['data.integration']) contains "shopify"
| summarize count() by message, bin_auto(_time)
```

Clean order-volume line: `| where message == "integrations.feed.OrderReceived"`.

**Unishippers (WWE) API usage:**

```apl
['REDACTED-DATASET-NAME']
| where orgId == "<id>"
| where message startswith "UnishippersService."
| extend flow = extract("UnishippersService\\.([a-zA-Z]+)", 1, message),
    direction = case(
        message endswith ": Request", "request",
        message endswith ": Response", "response",
        "other")
| where direction == "request"
| summarize count() by flow, bin_auto(_time)
```

**Pipedream transport — outbound p50/p95 latency** (runbook's `fields.*` → live `data.*`):

```apl
['REDACTED-DATASET-NAME']
| where ['data.metric'] == "pipedream.outbound.duration"
| extend duration = todouble(['data.durationMs'])
| summarize p50 = percentile(duration, 50), p95 = percentile(duration, 95), count = count()
  by ['data.providerSlug'], ['data.action'], bin_auto(_time)
```

**Pipedream — outbound error rate %:**

```apl
['REDACTED-DATASET-NAME']
| where ['data.metric'] == "pipedream.outbound.duration"
| summarize total = count(), errors = countif(['data.status'] != "ok") by ['data.providerSlug'], bin_auto(_time)
| extend errorRate = todouble(errors) / todouble(total) * 100
```

For an at-a-glance **Statistic**, collapse any of the above to a single number,
e.g. `| summarize ['Teams Events'] = count()` (drop the `by bin_auto(_time)`).
For an **evidence panel** (use a `Table`, not LogStream — that type does not
exist), e.g.
`| where orgId == "<id>" | project-keep _time, message, workflowName, requestId | order by _time desc | take 100`.

---

## Step 4 — Verify EVERY panel against the live dataset before it ships

No panel ships on an unverified query. For each candidate panel:

1. **Confirm fields exist.** Use Pi's `axiom` tool to project a single recent event and eyeball the fields:
    ```apl
    ['REDACTED-DATASET-NAME'] | where _time > ago(24h) | project orgId, channel, message, ['data.metric'] | take 1
    ```
2. **Dry-run the panel's APL** via Pi's `axiom` tool (`action='apl'`). Add `| take 5` (or a
   small `summarize`) and a tight time bound (`| where _time > ago(7d)`) so the
   dry-run is cheap. Axiom query calls rate-limit — run them sequentially, not in a
   batch.
3. A panel **passes** only if the query returns without error AND every field it
   references resolves. Zero rows is fine (e.g. a panel that goes live only after
   the next deploy) — a _field error_ is not. If a query errors, fix the field
   path (`fields.*` → `data.*` is the usual cause) and re-run before continuing.

Drop the `| take` / time bound from the final APL — the dashboard's
`timeWindow*` supplies the range.

---

## Step 5 — Build the DashboardDocument and SHOW it before POSTing

Design rule (from the official Axiom skill): **decisions first** — every panel
answers a question that leads to an action. Order panels top-down: at-a-glance
**Statistic** → trend **TimeSeries** → breakdown **Table** → evidence **Table**
(there is **no LogStream type** — see below). Prefer rates/percentiles over averages.

> ⚠ The schema below is **verified against the live API (2026-05-20, re-probed 2026-05-25)** — it is NOT the shape the older versions of this command described. The body must be wrapped in `{ "dashboard": { ... } }`.
>
> Top-level `description` **is accepted and persisted** (probed 2026-05-25: PUT 200, value survives a fresh GET) — set it to document each dashboard. `sparkline`, `unit`, `errorThreshold`, and `timeSeriesView` are still rejected with `400 invalid_dashboard: Unrecognized key`.
>
> Mirror the GET shape of an existing dashboard exactly (`GET /v2/dashboards` list → each item nests the real object under `.dashboard`). Build the payload with a Python script (UUIDs + exact keys), not by hand — avoids quoting hell and key drift.

Top level (inside the `dashboard` wrapper):

```json
{
    "name": "<scope-derived title>",
    "owner": "X-AXIOM-EVERYONE",
    "datasets": ["REDACTED-DATASET-NAME"],
    "refreshTime": 300,
    "schemaVersion": 2,
    "timeWindowStart": "qr-now-7d",
    "timeWindowEnd": "qr-now",
    "overrides": {},
    "charts": [],
    "layout": []
}
```

`refreshTime` ≥ 60: oncall `60`, team `300` (default), exec `900`. `owner` MUST be
`X-AXIOM-EVERYONE` — API tokens cannot create private dashboards. `overrides: {}`
is required. Server fills `uid`/`id`/`createdAt`/`version` — do not send them.

**Valid chart `type` values:** `Statistic`, `TimeSeries`, `Table`, `Pie`, `TopK`,
`SmartFilter`. **`LogStream` does not exist** — use `Table` with
`tableSettings.settings.showRaw = true` for log/evidence panels.

Every chart shares this base (APL lives at `query.apl` AND mirrored into
`query.queryOptions.editorContent`):

```jsonc
{
  "id": "<uuid4>",
  "name": "<panel title>",
  "type": "Statistic|TimeSeries|Table",
  "datasetId": "REDACTED-DATASET-NAME",   // singular, per-chart — NOT "datasets"
  "numSeries": 1,
  "modified": <epoch_ms>,
  "overrideDashboardCompareAgainst": false,
  "overrideDashboardTimeRange": false,
  "query": {
    "apl": "<final APL>",
    "endTime": "", "startTime": "", "libraries": [],
    "queryOptions": {
      "against": "", "aggChartOpts": "{}",
      "containsTimeFilter": "false",        // "false" when APL has no _time bound
      "editorContent": "<same APL>",
      "endTime": "", "startTime": "", "quickRange": ""
    }
  }
}
```

- **Statistic** adds: `"colorScheme": "Blue"`, `"showChart": <bool>` (true = sparkline).
- **TimeSeries**: base only.
- **Table** adds: `"tableSettings": { "columns": [], "settings": { "fitColumns": false, "fontSize": "12px", "hideNulls": true, "highlightSeverity": true, "isLive": "OFF", "showEvent": true, "showFieldList": false, "showHistory": false, "showRaw": true, "showSavedQueries": false, "showTimestamp": true, "wrapLines": true } }` (empty `columns` = auto).

Layout — one item per chart, 12-col row-major:
`{ "i": "<chartId>", "x": 0-11, "y": <int>, "w": 1-12, "h": <int>, "minH": 2, "minW": 2, "moved": false, "static": false }`.
Sensible grid: Statistic row `w:3 h:3` (four across), TimeSeries `w:6 h:4` (two
across), Table `w:12 h:6` full width.

**Then present to the user, and WAIT for confirmation:**

- A numbered list: each panel's **title + chart type + final APL**.
- A one-line plain-language summary per panel (what question it answers).
- The dashboard name, time window, and `orgId` (or "org-wide, no orgId filter").

Do NOT POST until the user confirms.

---

## Step 6 — Create the dashboard

Build the confirmed JSON with a Python script (UUIDs + exact keys from Step 5),
writing the **wrapped** payload `{ "dashboard": { ... } }` to a temp file — then
POST. The wrapper is mandatory: a bare object returns
`422 code 602 "dashboard in body is required"`.

Builder skeleton (fill `panels`, then run):

```python
import json, uuid, time
DS = "REDACTED-DATASET-NAME"; now = int(time.time()*1000)
def q(apl): return {"apl": apl, "endTime":"", "startTime":"", "libraries":[],
  "queryOptions":{"against":"","aggChartOpts":"{}","containsTimeFilter":"false",
    "editorContent":apl,"endTime":"","startTime":"","quickRange":""}}
TS = {"columns":[],"settings":{"fitColumns":False,"fontSize":"12px","hideNulls":True,
  "highlightSeverity":True,"isLive":"OFF","showEvent":True,"showFieldList":False,
  "showHistory":False,"showRaw":True,"showSavedQueries":False,"showTimestamp":True,"wrapLines":True}}
# panels: (name, type, apl, x, y, w, h, showChart_or_None)
panels = [ ... ]
charts=[]; layout=[]
for name,typ,apl,x,y,w,h,sc in panels:
    cid=str(uuid.uuid4())
    c={"id":cid,"name":name,"type":typ,"datasetId":DS,"numSeries":1,"modified":now,
       "overrideDashboardCompareAgainst":False,"overrideDashboardTimeRange":False,"query":q(apl)}
    if typ=="Statistic": c["colorScheme"]="Blue"; c["showChart"]=bool(sc)
    if typ=="Table": c["tableSettings"]=json.loads(json.dumps(TS))
    charts.append(c)
    layout.append({"i":cid,"x":x,"y":y,"w":w,"h":h,"minH":2,"minW":2,"moved":False,"static":False})
dash={"name":"<title>","datasets":[DS],"owner":"X-AXIOM-EVERYONE","refreshTime":300,
  "schemaVersion":2,"timeWindowStart":"qr-now-7d","timeWindowEnd":"qr-now",
  "overrides":{},"charts":charts,"layout":layout}
json.dump({"dashboard":dash}, open("/tmp/axiom_dashboard_final.json","w"))
```

```bash
# (env already loaded in Step 0; ENVFILE/AXIOM_TOKEN in scope)
curl -sS -w '\n%{http_code}' \
  -X POST "https://api.axiom.co/v2/dashboards" \
  -H "Authorization: Bearer $AXIOM_TOKEN" \
  -H "Content-Type: application/json" \
  --data @/tmp/axiom_dashboard_final.json   # contents: {"dashboard": {...}}
```

- **201** → the response wraps everything: `id` (short, e.g. `MEREpGcosVdYT5lbXO`)
  and `uid` (UUID) are at the **top level** of the response, and again under
  `.dashboard.uid`. Print both + panel count. Deep link is
  `https://app.axiom.co/<org-slug>/dashboards/<uid>`, but the **`<org-slug>` is not
  in the API response or `.env.local`** — substitute the user's Axiom slug or tell
  them to open the dashboard from the Axiom **Dashboards** sidebar by name. Never
  invent the slug.
- **4xx** → surface the Axiom error body **verbatim**, then fix the named cause:
    - `422 code 602 "dashboard in body is required"` → payload not wrapped in
      `{"dashboard": …}`.
    - `400 invalid_dashboard "Unrecognized key: <k>"` → a stale field (`sparkline`,
      `unit`, `timeSeriesView`, `errorThreshold`). Strip it; the response names the
      offending `[charts N]` index. (`description` is **accepted** — see below.)
    - `401` → token lacks dashboard-write scope (mint a PAT).
      Do not silently retry.

To update later: `PATCH /v2/dashboards/uid/{uid}` (same wrapped body).
To fetch one: `GET /v2/dashboards/uid/{uid}` — **note `/uid/` segment**; the list
endpoint's short `id` is NOT a valid GET path (`GET /v2/dashboards/<id>` → 404).
The list endpoint `GET /v2/dashboards` returns items that nest the real object
under `.dashboard` — that nested object is the exact shape to mirror for new charts.

---

## Sibling: monitors-as-code (alerting)

Dashboards show state; **monitors page**. This command builds dashboards only —
alerting lives in `axiom/monitors/*.json` + `axiom/deploy-monitors.sh`, deployed
the same source-of-truth way (see `axiom/README.md` → "Axiom monitors-as-code").
A monitor is the alerting twin of a dashboard panel: same APL, same `.env.local`
token, but it POSTs to `/v2/monitors` (and a `/v2/notifiers` Slack notifier)
instead of `/v2/dashboards`.

Reach for a monitor (not a panel) when the answer should **page** someone:
a failure-rate threshold, a latency SLO breach, a dead pipeline. Key API
differences from dashboards:

- Write is **POST** `/v2/monitors` (create) / **PUT** `/v2/monitors/{id}`
  (update, **bare object — no `version` wrapper**).
- `type:"Threshold"` + `operator` + `threshold`; `summarize … by <dim>` with
  `notifyByGroup:true` fans one alert per group (e.g. per provider).
- `alertOnNoData:true` + a `Below` count threshold = dead-pipeline monitor.
- Notifier: **POST** `/v2/notifiers` `{name, properties:{webhook:{url}}}` (Slack
  incoming webhook). Resolve by name, inject id into each monitor's `notifierIds`.

To ship one, add `axiom/monitors/<slug>.json` and run `./axiom/deploy-monitors.sh`.

---

## Out of scope

No in-app UI, no scheduled refresh, no name→orgId lookup (always prompt), no
dependency on the `axiomhq/skills` bash scripts at runtime (they use
`~/.axiom.toml`, not our `.env.local` — we mirror their JSON shape and do our own
curl). Alerting is **not** built here — it lives in `axiom/monitors/` (see the
sibling note above), not in this dashboard command.
