---
description: Commit + push + open PR (reviews fire automatically — Arbiter/Devin/Codex). Pass PR# to check review status only.
argument-hint: [optional: PR number or URL to skip create and check review status only]
model: sonnet
---

# /ship $ARGUMENTS

Commit → push → PR (reviews fire automatically on open/push). PR body chooses **small** or **rich**
shape from diff size/risk. Meaningful code PRs include Changed / Preserved + tests. Work lives
in repo + local ticket tree.

## 0. Pre-flight (parallel)

Parse `$ARGUMENTS`: non-empty token → PR number/URL → `PR_TARGET=<x>`, **skip §1–§3,
jump §4**.

Run in parallel and cache outputs — §2.5 + §3 reuse, never re-run:
- `git status --porcelain`
- `git branch --show-current`
- `git rev-parse --abbrev-ref --symbolic-full-name @{u}` (allow failure)
- `git log --oneline origin/main..HEAD` → `LOG_LINES`
- `git diff --stat origin/main...HEAD` → `DIFF_STAT`
- `gh pr view --json number,url,state,title 2>/dev/null`

**Stop conditions** (report, wait):
- On `main`/`master` → refuse.
- No commits ahead AND clean AND no PR → ask what was meant.

## 1. Commit (only if dirty)

Conventional-commit subject ≤50 chars (`feat:`/`fix:`/`refactor:`/`chore:`/etc.). Body only
when "why" isn't obvious from the diff. Stage explicitly — never `git add -A` blind. Unsure
→ ask. Never bypass hooks. Pre-commit fails → fix root cause, new commit, no `--amend`.

Clean + commits ahead → skip to §2.

## 2. Push

`git push -u origin HEAD`. Rejected → `git pull --rebase`, resolve, push again. Surface
conflicts; don't resolve silently.

## 2.5. Linear ticket (always linked)

Every PR carries `[<TICKET_ID>] <desc>` so it links to a ticket with description, reasoning,
implementation, assignee. New tickets are created on the **AOA** team (`AO - Agents`). The old
`AE` / `Autonomy Eng` team is **retired** — creating there fails with
`GraphQL error: Entity is retired: team`. Existing briefs still carrying `linear: AE-NNNN`
are reconciled in place: reuse the id, never re-create it on AOA.

1. **Resolve brief** from current branch. Reuse `wt --resolve` if available; else
   `grep -rlE "^linear:" "${TICKETS_DIR:-$HOME/.claude/tickets}" --include='*.md'` matched
   by branch slug in filename or `## Local notes`. Found → `BRIEF_FILE=<path>`.
2. **Read `linear:` frontmatter** from `$BRIEF_FILE` (if any). Non-empty → `TICKET_ID=<that>`,
   **skip to §3**.
3. **No linked ticket** → create one. Script composes body itself from git — do NOT build
   description/reasoning/implementation bullets here, do NOT pass `--description`:
   ```
   LINEAR_TICKET_CREATE_OK=1 ~/.dotfiles/scripts/linear-ticket.py create \
     --team "AOA" \
     --title "<≤80 chars, action-oriented, no id prefix — Linear adds its own ID>" \
     --state "In Progress" \
     --assignee me \
     --auto-body origin/main \
     --labels "<from brief frontmatter labels:, comma-sep — omit flag if none>"
   ```
   `--auto-body origin/main` triggers the script's `compose_body_from_git`: dedup subjects
   → Description, commit `%b` paragraphs → Reasoning, `git diff --stat` grouped by top-dir
   → Implementation. `state` = `In Progress` because work is done (PR is the deliverable).
   stdout on success: `AOA-NNN<TAB>url`.
4. **Capture the id** from stdout → `TICKET_ID`. Brief exists → write `linear: <TICKET_ID>`
   back into its frontmatter so future runs reuse. Brief missing → skip writeback.
5. **Script failure** (nonzero exit: no key, network, team not found) → reason on stderr.
   Log one line, set `TICKET_ID=""`, continue with no-prefix title. Don't block ship. Never
   substitute a different team on your own — report the failure and let the user decide.

## 3. PR body — choose sparse vs rich deliberately

If `.github/PULL_REQUEST_TEMPLATE.md` exists, fill its sections with the shape below.
Default to the rich shape when reviewers need context; sparse bodies are only for obviously
small, single-purpose changes.

### Small PR shape

Use only when the branch touches a few files and does not add/change providers, external APIs,
schemas, workflows, routing, auth, persistence, observability, or multi-subsystem behavior.

```
Linear: https://linear.app/<workspace>/issue/<TICKET_ID>

## Summary

### Changed
- <structural change>

### Preserved
- <load-bearing behavior unchanged>

## Tests
- <verification step and result>
```

### Large / platform / integration PR shape

Use when the diff adds or changes integrations, providers, external APIs, schemas, workflows,
routing, auth, persistence, observability, generated tests, or crosses multiple subsystems.

```
## Linear ticket

[<TICKET_ID>](https://linear.app/<workspace>/issue/<TICKET_ID>)

## Summary

### Changed
- <new capability or interface>
- <wiring / schema / workflow change>
- <operational behavior change>

### Preserved
- <existing behavior intentionally unchanged>
- <compatibility / default / fallback behavior>
- <blast-radius limit or no-new-dependency/index/migration note>

## Automated tests added

- `<test file>` — <behavior covered>.

## Manual testing steps

- `<command>` ✅
- `<command>` ⚠️ <known existing failure or credential/staging blocker>
- <post-credential or production smoke step, if applicable>
```

Rules: "Preserved" reassures reviewers blast radius is small. Keep bullets one line where
practical; allow short phrases for test coverage and manual blockers. List new/changed test
files separately from commands for non-trivial diffs. No emoji, no generated-with footer unless
repo convention. Derive bullets from the **cached** `LOG_LINES` + `DIFF_STAT` from §0 — don't
re-run git. Abstract, don't restate.

Then `gh pr create`:
- `--title`: `$TICKET_ID` non-empty → `[<TICKET_ID>] <desc>` (≤70 chars total).
  Empty → action-oriented title, no ID prefix.
- `--body` from shape above via heredoc.
- `--base` usually `main`; for `*/slice-N` branches infer parent from `git log`, confirm
  if ambiguous.
- `--draft` only if obviously incomplete (TODO commits, failing local checks).

Capture URL.

## 4. Review — automatic, nothing to trigger

**Chuck is RETIRED (2026-08-04) — never tag `@chuck-noland-cartage`, never poll for a
`chuck-noland[bot]` comment.** Reviews now fire automatically on PR open/push:

- **Devin** (`devin-ai-integration[bot]`) + **Codex** post normal GitHub Review objects
  with inline comments (`pulls/<PR>/comments`).
- **Arbiter** (`.github/workflows/arbiter.yml`, where present — e.g. `cartage-agent`)
  synthesizes reviewer output + diff + CI into a REQUIRED `arbiter` commit status
  (`approve`=success, `block`/`needs-human`=failure) plus an issue comment from
  `github-actions[bot]` starting `<!-- arbiter-verdict -->`. A new push resets it to
  `pending` and re-reviews automatically.

/ship posts nothing and does not wait. To check status later:
`gh api repos/{owner}/{repo}/commits/<head-sha>/status --jq '.statuses[] | select(.context=="arbiter")'`.
Address findings via `/address-feedback`.

## 5. Report — terse

```
PR: <url>
Review: <automatic — arbiter status pending | no arbiter in this repo>
```

Clean nothing-to-do → say so in one line.

## 6. Stop

Cockpit sessions only: do not auto-fix. Do not amend the PR description. Do not request
reviewers. User decides. Single-character blocker spotted (typo, obvious null guard) →
call out exact fix, still wait for "go" before editing.

In a `wt` lane, /ship returning is NOT the end of the lane — the lane continues into the
review-feedback loop (poll the `arbiter` commit status, address findings on `block`, push,
`lane-done.sh` on `approve`) per its kickoff prompt and global CLAUDE.md §Autonomous
semantics.
