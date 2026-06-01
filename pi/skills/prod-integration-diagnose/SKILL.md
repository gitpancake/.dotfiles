---
name: prod-integration-diagnose
description: Production integration debugging loop for vendor/API failures. Use when comparing a failing customer/org/document against a known-good org, investigating opaque vendor 500s, carrier booking failures, webhook/action regressions, or asking what changed since last success. Combines Axiom logs, persisted state, code history, and regression tests.
---

# Prod Integration Diagnose

Debug production integration failures by diffing a failing case against a known-good case at the same external boundary. Do not debug the failing case alone.

Load the general `diagnose` skill too if available. This skill specializes that loop for production vendor/API integrations.

## Operating contract

- Read project `AGENTS.md` / `CLAUDE.md` first when inside a repo.
- Check `git status --short --branch` before editing.
- Prefer read-only evidence first: logs, traces, persisted docs, git history.
- Preserve context by writing durable debug artifacts before doing broad log/doc pulls.
- Never print secrets, auth tokens, raw credential fields, customer emails, or phone numbers.
- Never mutate production data. Firestore/API inspection is read-only unless the user explicitly asks and the repo rules allow it.
- Never execute known destructive scripts. In Cartage, never run `deleteDocsByOrgId.script.ts`.
- Do not speculate. Every hypothesis needs the probe that would falsify it.
- Do not fix until the external-boundary difference is proven or the remaining uncertainty is stated.

## Required frame

Extract or ask for these fields. If the prompt gives enough context, proceed without grilling. Write the frame to the debug artifact as soon as it is known.

```markdown
Failing:
- org/customer:
- orgId:
- document/run/request id:
- vendor/provider:
- action/endpoint:
- carrier/account/entity if relevant:
- timestamp/window:
- observed error:

Known-good comparator:
- org/customer:
- orgId:
- document/run/request id:
- same vendor/action? yes/no:
- last successful timestamp/window:
- why it should be equivalent:
```

If there is no known-good comparator, find one from logs before deep code reading: same vendor, same action, closest success, then same carrier/account if possible.

## Context-preserving artifact workflow

Do this before expensive queries or code archaeology unless the user explicitly asks for a chat-only answer.

1. Create a durable working directory:
   - In a repo: `.debug/prod-debug/<vendor>-<action>-<org-or-doc>-<YYYY-MM-DD>/`
   - Outside a repo: `/tmp/prod-debug/<vendor>-<action>-<org-or-doc>-<YYYY-MM-DD>/`
2. Copy the template from `ARTIFACT_TEMPLATE.md` into `artifact.md` and fill it incrementally.
3. Save raw or verbose outputs to files, not chat:
   - `axiom-queries.apl`
   - `axiom-results.jsonl` or `axiom-results.md`
   - `firestore-normalized.json`
   - `source-notes.md`
4. In chat, report only evidence cards: boundary, IDs, counts, normalized request-shape diff, verdict, next probe.
5. Store stable references to raw evidence: request IDs, run IDs, document IDs, commit SHAs, and artifact file paths.
6. If the session crosses ~30–40% context or before switching tasks, update the `Current verdict`, `Stable references`, and `Remaining unknowns` sections.

Never paste large raw Axiom rows or whole customer docs into chat. Redact and summarize in tables; keep raw evidence in the artifact file system.

## Loop

### 1. Build the pass/fail boundary

Name the exact boundary that fails:

- external endpoint/action, webhook, carrier booking, OAuth callback, sync job, etc.
- request id / run id / async task id if present
- success signal and failure signal

Prefer a replayable fixture/test if safe. If production replay could book/charge/mutate, do not replay; use captured payloads and mocked responses.

### 2. Runtime truth: Axiom / traces

Use `axiom` with tight time bounds and projected fields. Prefer compact output. Save every query to `axiom-queries.apl`; save verbose/raw results to an artifact file and chat only the evidence card.

Reject your own query and narrow it if it returns broad raw blobs without a clear projection. Prefer fields like `_time`, `level`, `message`, `orgId`, `orgName`, `requestId`, `runId`, `workflowName`, `data.responseStatus`, `data.responseData.ResponseStatus`, and boundary-specific request-shape fields.

Queries to adapt:

```apl
['REDACTED-DATASET-NAME']
| where _time > ago(7d)
| where orgId == "<failingOrgId>"
| where message contains "<vendor>" or tostring(data) contains "<endpointOrAction>"
| project _time, level, message, orgId, orgName, requestId, runId, workflowName,
    vendorStatus=tostring(data.responseStatus),
    vendorError=tostring(data.responseData.ResponseStatus),
    shipmentId=tostring(data.shipmentId),
    carrier=tostring(data.CarrierSCAC)
| order by _time desc
| take 50
```

```apl
['REDACTED-DATASET-NAME']
| where _time > ago(30d)
| where orgId == "<knownGoodOrgId>"
| where message contains "<vendor>" or tostring(data) contains "<endpointOrAction>"
| project _time, level, message, orgId, orgName, requestId, runId, workflowName,
    vendorStatus=tostring(data.responseStatus),
    vendorError=tostring(data.responseData.ResponseStatus),
    shipmentId=tostring(data.shipmentId),
    carrier=tostring(data.CarrierSCAC)
| order by _time desc
| take 50
```

If carrier/entity matters:

```apl
['REDACTED-DATASET-NAME']
| where _time > ago(30d)
| where message contains "<vendor>" or tostring(data) contains "<vendor>"
| where tostring(data) contains "<carrierOrEntity>"
| project _time, orgId, orgName, message, requestId, runId,
    vendorStatus=tostring(data.responseStatus),
    vendorError=tostring(data.responseData.ResponseStatus),
    shipmentId=tostring(data.shipmentId),
    carrier=tostring(data.CarrierSCAC)
| order by _time desc
| take 100
```

If a LangSmith run id appears, use `langsmith` or `debug_observability` once to correlate tool decisions with logs.

Record an evidence card in `artifact.md`:

```json
{
  "boundary": "<vendor endpoint/action>",
  "failures": [
    {
      "time": "<iso>",
      "orgId": "<id>",
      "requestId": "<id>",
      "runId": "<id>",
      "vendorStatus": "<status>",
      "vendorError": "<normalized error>"
    }
  ],
  "knownGood": [],
  "requestShapeDiff": [
    { "field": "<field>", "failing": "<value>", "knownGood": "<value>", "verdict": "<ok/suspicious>" }
  ],
  "rawEvidence": ["<artifact path or stable query ref>"]
}
```

Capture:

- exact request payload shape sent to the vendor, normalized to boundary-relevant fields
- exact response/error shape
- success payload shape from the comparator
- request ids / run ids connecting logs
- fields present in success but absent/null in failure

### 3. Persisted truth: production documents, read-only

Read the failing and known-good documents from the source of truth. In Cartage, Firestore reads via `gcloud auth print-access-token` + REST are acceptable when read-only and secrets are not printed.

Use a temp file or pipe to Python for JSON normalization. Do not echo tokens. Redact obvious secrets before presenting.

Compare normalized docs at the business boundary. Write the normalized subset to `firestore-normalized.json`; chat only the diff table.

- orgId / account config references
- stops / addresses / dates
- commodities / dimensions / weights / classes
- accessorials / nullable collections / optional arrays
- quotes / selected carrier / service level
- opaque tokens only if decoding is safe and not secret-bearing; decode to identify non-secret routing info like carrier name, not credentials
- fields included in the vendor request builder

Output a diff table instead of dumping whole docs:

```markdown
| Field | Failing | Known-good | Verdict |
| --- | --- | --- | --- |
| accessorials | null | [] | suspicious: request builder may expect array |
```

### 4. Code archaeology

Use `git log`, `git show`, and targeted search to answer:

- when did the known-good case last succeed?
- what changed in the integration since then?
- which files build the failing request payload?
- which tests cover this boundary?
- are there sibling providers/adapters with the same pattern?

Read only the relevant files first: service wrapper, workflow, router/tool caller, schema/types, tests, docs embedded in repo. Record commit SHAs and file paths in the artifact instead of pasting diffs unless the exact hunk is necessary.

### 5. Hypotheses

Before fixing, write 3–5 ranked hypotheses with falsifiable probes. Put the full table in the artifact and summarize the top 1–2 in chat.

Format:

```markdown
1. <hypothesis>
   Prediction: if true, <probe> will show <result>.
   Probe: <Axiom/Firestore/git/test command>.
   Result: pending/proven/killed.
```

Kill common false trails explicitly when evidence supports it, e.g. credentials enabled, carrier contracted, account mismatch, stale token, weight/class issue, nullable optional fields.

### 6. Fix

Only after evidence points to a root cause:

- make the smallest code change at the boundary that handles the real data shape
- preserve architecture: service wrappers stay thin, workflows own business logic, routers auth/validate/call workflows
- use project error handling rules (`XError`, logging, no silent catches) where applicable
- run prettier on modified files
- run the project verification command (`bun type-check` in Cartage)

### 7. Regression

Add or generate the regression at the correct seam:

- captured payload/request builder test for nullable/missing fields
- workflow test if the bug needs document → request transformation
- generated Wilson test only when the failure is Wilson behavior and a LangSmith run is provided

The test must fail before the fix if practical. If no good seam exists, state that as a finding and propose a follow-up.

### 8. Scope / memory handoff

If follow-up work remains, use `/scope` or create a brief with:

- root cause
- exact evidence
- files touched / files to start in
- remaining unknowns
- acceptance criteria
- regression test expectation

## Output discipline

- Chat updates should be short: verdict, changed confidence, next probe, and artifact path.
- Full state lives in `artifact.md`.
- Any final report should reference the artifact path and stable IDs.
- If no artifact was created, say why.

## Final report shape

```markdown
## Prod Integration Diagnosis: <vendor/action>

**Verdict:** <root cause or narrowed finding>
**Failing:** <org/doc/action>
**Known-good:** <org/doc/action>

### Evidence
- Runtime: <Axiom/log/trace findings>
- Persisted state: <doc diff findings>
- Code history: <relevant commits/PRs>

### Hypotheses
| # | Hypothesis | Result | Evidence |
| --- | --- | --- | --- |

### Fix
- <files/changes or plan>

### Regression
- <test/command>

### Remaining unknowns
- <only if any>
```

## Native prompt

For an interactive entrypoint, use `/prod-debug` with the failing case and known-good comparator. This skill is the workflow behind that prompt.
