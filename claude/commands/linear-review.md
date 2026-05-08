---
description: Audit user's Linear tickets — cross-reference GitHub PRs, flag stale / duplicate / forgotten / irrelevant tickets, propose state cleanups. Read-only by default; mutations only on explicit go.
argument-hint: [optional: team slug, e.g. AE or AUT]
---

# /linear-review $ARGUMENTS

user creates a lot of Linear tickets (`/scope`, ad-hoc, follow-ups from PRs). This drifts. Goal: surface what should be closed, deduped, marked done, or revisited — backed by signal, not vibes.

This command is **read-only by default**. It produces a proposed action plan in §6 and stops. Only on user's "go" does it execute mutations in §7 — and even then, batched and confirmable.

If `$ARGUMENTS` is given, scope to that team (`AE`, `AUT`, etc.). Otherwise scope to all teams user is assigned in.

## 1. Pull state (parallel)

Run in parallel. Cap each list at 200 to keep this cheap.

- `mcp__linear-server__list_issues` — assignee = me, state ∉ {Done, Cancelled, Duplicate}, ordered by `updatedAt` desc.
- `mcp__linear-server__list_issues` — assignee = me, state = "In Progress" (separate fetch — these get extra scrutiny).
- `mcp__linear-server__list_issues` — created by me in last 90 days (user creates tickets others may be assigned to).
- `mcp__linear-server__list_my_issues` if available, otherwise the above suffice.
- `gh pr list --author "@me" --state all --limit 100 --json number,title,state,url,headRefName,createdAt,closedAt,mergedAt,body`
- `gh pr list --search "involves:@me" --state open --limit 50 --json number,title,state,url,headRefName,body` — PRs where user is reviewer / mentioned.

## 2. Cross-reference PRs ↔ tickets

For each PR, extract ticket IDs from:
- Branch name (`agent/team-1530`, `feature/team-1450-…`, `henry/team-1462-…`).
- PR title (`[TEAM-1530] …`).
- PR body (URLs / IDs anywhere).

Build a map: `{ticketId → [pr1, pr2, …]}` and `{prNumber → [ticketId, …]}`.

Note: example-org uses prefixes `AE`, `AUT`, `ENG`, `PRO`. Match them all. Lowercase variants too (branch names).

## 3. Categorize

For each open ticket, assign to **at most one** category. Earlier categories take precedence. If nothing applies, the ticket is healthy — don't list it.

### A. `merged-but-not-done`
- Ticket state ∈ {In Progress, In Review, Backlog, Todo}, AND
- A PR referencing this ticket is **merged**.
- → Propose: state → Done.

### B. `pr-closed-not-reopened`
- Ticket state ∈ {In Progress, In Review}, AND
- A PR referencing this ticket is **closed (not merged)** and there's no newer open PR.
- → Propose: comment on ticket asking whether to revive or close; state → Backlog if no user-comment in 30+ days.

### C. `in-progress-stale`
- Ticket state = "In Progress", AND
- No update (comment or status change) in 21+ days, AND
- No active PR.
- → Propose: state → Backlog (or Done if work is clearly elsewhere). Add reason in comment.

### D. `duplicates`
- Two or more tickets with same/very-similar titles (Levenshtein < 5 on normalized title) OR same first-line of body.
- → Propose: keep the **earlier-created** one (or the one that has a PR); duplicate-mark the others (state = Duplicate, link to canonical via `mcp__linear-server__update_issue` adding "duplicate of" link in description).

### E. `stale-backlog`
- State = Backlog or Todo, AND
- No updates in 60+ days, AND
- No PRs reference it, AND
- Priority is None or Low.
- → Propose: close (state = Cancelled) with comment "Closed by /linear-review — no activity in N days, no priority, no PR. Re-open if still relevant."

### F. `forgotten-high-prio`
- State ∈ {Backlog, Todo, In Progress}, AND
- Priority ∈ {Urgent, High}, AND
- No update in 14+ days.
- → Propose: surface for re-prioritization. **No mutation** — just flag. user decides.

### G. `irrelevant`
- Heuristic only — flag for human review:
  - Title mentions a project/vendor that's been sunset (llm-observability, cloud task queue, sandbox-vendor for new work).
  - Or title references a customer user no longer owns.
- → Propose: flag for review, optional comment from user.

## 4. Sanity-pass with comments

For each candidate in A–E (the actionable categories), fetch the last 3 comments (`mcp__linear-server__list_comments`) before proposing the mutation. If the most recent comment says "blocked", "waiting on", "user will", "not yet" — **downgrade** the proposal:
- A → still propose (a merged PR is hard signal)
- B / C / E → demote to "flag, don't mutate"
- D → still propose (dup signal is structural)

## 4.5 Interactive disambiguation — ask by title, not ID

For tickets where the signal is ambiguous (last comment is unclear, no comments at all but state is In Progress, or duplicate-match is borderline), **ask user directly** before placing the ticket into a category. Use the **title** as the anchor, not the ID — user remembers titles, not IDs.

Question shapes (one ticket per question, batch where possible):

> Still working on **"<Ticket title>"**? It's been in *In Progress* for 24 days with no PR or comments.
> - **Yes, still active** → leave as-is
> - **No, drop it** → state → Backlog with comment "Closed by /linear-review — confirmed not active"
> - **Done already** → state → Done with comment "Closed by /linear-review — confirmed complete"
> - **Don't recognize this** → state → Backlog, flag for /read-ticket review

For dup-match borderline cases:

> **"<Title A>"** and **"<Title B>"** look duplicate (similarity X%). Same work?
> - **Yes, dup B** → keep A canonical, mark B Duplicate
> - **Yes, dup A** → keep B canonical, mark A Duplicate
> - **No, different** → leave both, don't flag again

Trigger an interactive question when **any** of:
- State = In Progress AND no comments AND no PR AND age > 14 days.
- Title matches a current focus area (Shopify, Teams, CarrierA) AND status is Backlog AND age > 14 days — user should at least see it.
- Dup-match similarity is between 60% and 90% (above 90% → confidently propose; below 60% → don't even raise).
- Last comment is from user himself but contains "?" or "TODO" — he was thinking about it.

Ask via `AskUserQuestion`-style prompts when the harness supports it; otherwise inline prose with a numbered list, one question at a time. Wait for the answer before moving on.

**Cap**: max 8 interactive questions per run. If there are more, batch the rest into the §6 "flag only" categories — don't drown user in prompts.

user's answers update the candidate categorization in-memory before §6's report. The §6 report should reflect his answers ("confirmed not active by user").

## 5. Open-PR inventory (no mutation)

Independent section: list every open PR user authored or is assigned to review.

For each PR:
- Number, title, state (open / draft / changes-requested / approved).
- Linked ticket(s) — show "—" if none, flagged as `unlinked-pr`.
- CI state (use `gh pr checks <num>` if cheap; skip if it would balloon tool calls).
- Last activity timestamp.

`unlinked-pr` is a flag-only category — no auto-link.

## 6. Report — single document. Stop.

Lead with **title**, follow with ID in parentheses. user recognizes by title.

```
LINEAR REVIEW — <team(s)> — <YYYY-MM-DD>
Tickets scanned: <N>     Open PRs scanned: <M>     Cross-ref matches: <K>     Interactive Qs: <Q>

═══ Proposed mutations (require "go") ═══

A. Merged-but-not-done  (state → Done)
| Title | ID | PR | Confirmed by |
| "Refactor Shopify webhook for isTestEnv" | TEAM-1530 | #3142 merged 2026-04-29 | merged-PR |

B. PR closed, not reopened  (comment + state → Backlog)
| Title | ID | PR | Closed | Last user-comment |

C. In-progress stale  (state → Backlog)
| Title | ID | Days idle | Confirmed by |
| "Telegram org-resolution" | TEAM-518 | 23 | user-confirmed-inactive |

D. Duplicates  (keep earlier, mark others Duplicate)
| Canonical title (ID) | Duplicate title (ID) | Confirmed by |

E. Stale backlog, no priority  (state → Cancelled)
| Title | ID | Days idle |

═══ Flag only — no auto-action ═══

F. Forgotten high-prio
| Title | ID | Priority | Days idle |

G. Irrelevant / sunset-stack
| Title | ID | Why flagged |

H. Unlinked PRs
| PR | PR title | State |

═══ Open PR inventory ═══
| PR | Title | State | Linked ticket title | Last activity |
```

`Confirmed by` column values:
- `merged-PR` / `closed-PR` — hard signal from GitHub
- `idle-21d` / `idle-60d` — age-based
- `user-confirmed-active` / `user-confirmed-inactive` / `user-confirmed-done` — user answered an interactive question
- `dup-95%-similar` — high-confidence dup match
- `last-comment-blocked` — sanity-pass downgrade reason

Then one line:

> `Run /linear-review go` to execute mutations in A–E, or `/linear-review go A,D` to scope to specific categories.

**Stop.** No mutations yet.

## 7. On "go": execute

When user sends `go` (or `go <categories>`), execute the proposed mutations for the selected categories.

Per-mutation, in this order:
- D first (duplicates) — collapse the graph before other mutations on the same ticket.
- A (merged-but-not-done).
- E (stale backlog cancel).
- C (in-progress stale → Backlog).
- B (PR closed not reopened) — only if `$ARGUMENTS` includes B explicitly; otherwise flag.

For each mutation:
- `mcp__linear-server__update_issue` for state changes.
- `mcp__linear-server__save_comment` for the explanation comment (always).
- For duplicates: also update description to add `Duplicate of <ID>` link near the top.

Print a transaction log:
```
[DONE]  TEAM-1234  state: In Progress → Done    reason: PR #3142 merged
[DONE]  TEAM-1235  state: Backlog → Cancelled    reason: 73 days idle, no PR, no priority
[SKIP]  TEAM-1236  reason: comment within 7 days mentioned "waiting on Alex"
…
```

After all mutations, post a summary:
- Total mutated.
- Total skipped (with reason).
- Any failures (`mcp__linear-server__update_issue` non-200 etc.).

## 8. Hard rules

- **Never mutate** a ticket without a comment explaining why.
- **Never mutate** a ticket whose last comment author is not user (someone else is engaged — leave it).
- **Never mutate** a ticket linked to a PR with state = open. Open PRs are live work.
- **Never mutate** anything in §6 categories F, G, H — those are flag-only.
- **Never delete**. Use Cancelled or Duplicate states.
- If `mcp__linear-server` call fails, surface the error verbatim — do not retry with a guess.

## 9. Stop conditions

- After §6 — wait for `go` or no-go.
- After §7 — print summary, then stop. Do not loop or re-scan.
