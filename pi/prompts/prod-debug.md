---
description: Debug a production vendor/API integration failure by diffing failing vs known-good evidence.
argument-hint: "<failing case> [--known-good ...] [--vendor ...] [--action ...]"
---

# /prod-debug $ARGUMENTS

Use the `prod-integration-diagnose` skill. If available, also load the general `diagnose` skill for the reproduce → hypothesize → instrument → fix loop.

Debug this production integration failure by comparing the failing case against a known-good case at the same external boundary:

```text
$ARGUMENTS
```

## Start

1. Read project `AGENTS.md` / `CLAUDE.md` if inside a repo.
2. Check `git status --short --branch` before editing.
3. Extract the debug frame from the prompt:

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

If required fields are missing but discoverable from PRs, logs, docs, or the repo, discover them. Ask only when blocked.

## Evidence order

Do not jump straight to code. Gather evidence in this order:

1. **Runtime truth** — Axiom/logs/traces for failing and known-good cases.
2. **Persisted truth** — read-only production docs/config/state for both cases.
3. **Code history** — git log/show around the integration since last known success.
4. **Source** — request builder, service wrapper, workflow, schema/types, tests.
5. **Hypotheses** — 3–5 ranked, falsifiable, with probes.
6. **Fix + regression** — only after the root cause or narrowed diff is proven.

## Default Axiom probes

Adapt these with tight time windows and only projected fields:

```apl
['REDACTED-DATASET-NAME']
| where _time > ago(7d)
| where orgId == "<failingOrgId>"
| where message contains "<vendor>" or tostring(data) contains "<actionOrEndpoint>"
| project _time, level, message, orgId, orgName, requestId, runId, workflowName, error, data
| order by _time desc
| take 50
```

```apl
['REDACTED-DATASET-NAME']
| where _time > ago(30d)
| where orgId == "<knownGoodOrgId>"
| where message contains "<vendor>" or tostring(data) contains "<actionOrEndpoint>"
| project _time, level, message, orgId, orgName, requestId, runId, workflowName, error, data
| order by _time desc
| take 50
```

## Firestore / production state rule

Production state inspection must be read-only. Use existing repo scripts if present; otherwise use safe `gcloud`/REST reads without printing access tokens. Normalize and redact before reporting. Compare documents as a table; do not dump entire customer records unless necessary.

## Report format

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

If the fix is implemented, run the project verification command and use `/scope` for any follow-up brief.
