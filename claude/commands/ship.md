---
description: Commit + push + open PR (reviews fire automatically — Arbiter/Devin/Codex).
model: sonnet
---

# /ship $ARGUMENTS

Commit → push → PR (reviews fire automatically on open/push — nothing to trigger, see
`~/.claude/docs/lane-protocol.md` for the review loop). Work lives in repo + local ticket tree.

## 0. Pre-flight (parallel)

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
implementation, assignee. New tickets → **AOA** team (full teams doctrine, incl. the retired
AE team and id reconciliation: global CLAUDE.md §Linear teams).

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

## 3. PR body — repo template first, always

**If `.github/PULL_REQUEST_TEMPLATE.md` exists, the body MUST use its sections verbatim —
every heading present, genuinely filled in (`N/A` + one-line justification beats omitting a
section), none replaced or renamed.** The Arbiter gate 🔴-blocks bodies that swap template
sections for ad-hoc headings (learned on PR #6490). Org-specific section notes:
`~/.claude/org/<org>/preamble.md`. Depth inside the sections scales with diff size/risk.

**No template in the repo** → compose: Linear link, `## Summary` with `### Changed` +
`### Preserved` (blast-radius reassurance), tests (automated + manual verification for
non-trivial diffs). Scale depth to the diff — a platform/integration PR earns full
test/manual-steps detail; a small fix doesn't. Derive bullets from the **cached**
`LOG_LINES` + `DIFF_STAT` from §0 — don't re-run git. Abstract, don't restate.

Then `gh pr create`:
- `--title`: `$TICKET_ID` non-empty → `[<TICKET_ID>] <desc>` (≤70 chars total).
  Empty → action-oriented title, no ID prefix.
- `--body` from shape above via heredoc.
- `--base` usually `main`; for `*/slice-N` branches infer parent from `git log`, confirm
  if ambiguous.
- `--draft` only if obviously incomplete (TODO commits, failing local checks).

Capture URL.

## 4. Review — automatic, nothing to trigger

Reviews fire automatically on PR open/push (Arbiter/Devin/Codex — mechanics + poll command:
`~/.claude/docs/lane-protocol.md`). /ship posts nothing and does not wait. Address findings
via `/address-feedback`.

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
review loop per `~/.claude/docs/lane-protocol.md`.
