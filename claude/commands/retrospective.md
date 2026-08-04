---
description: Retro on completed integration/feature. GH PRs + git + local ticket tree → Notion.
argument-hint: <integration-name or free-text scope>
---

# /retrospective $ARGUMENTS

Data-driven retrospective on a completed feature or integration. Pulls from GitHub PRs, git commits, and the local ticket tree (`$TICKETS_DIR`) to build a structured retro, then publishes to Notion under the Engineering page. Linear is **not** a read source here — it has no MCP in this setup (write-only via `scripts/linear-ticket.py`); ticket state comes from the local tree, which is the source of truth.

If `$ARGUMENTS` is empty, infer from conversation context — what integration or feature was just discussed, shipped, or closed. State the inferred scope in one sentence and proceed to §1. If no context either, ask and stop.

## §1. Scope

Parse `$ARGUMENTS` for:
- **Integration/feature name** (e.g., "Shopify", "Teams L3") — required.
- **Date range** — if not given, default to last 3 weeks.
- **Repo path** — if not given, check `$PWD`, then scan `~/Documents/code/`.

If name is missing or ambiguous, ask what's needed to pin it down and stop until answered. Don't proceed to §2 with a vague scope — the git and PR queries depend on having a concrete keyword set.

Print the resolved scope + date range before continuing:

```
Scope:  <name>
From:   <start-date>  To:  <end-date>
Repo:   <path>
```

## §2. Data collection (parallel)

Run all in parallel. Use the resolved name to build keyword search strings.

- `gh pr list --state all --limit 200 --json number,title,state,createdAt,mergedAt,headRefName,additions,deletions,closedAt,body --search "<keywords>"` — all PRs matching the integration name.
- `git log --all --since="<start>" --until="<end>" --oneline --decorate` — full commit timeline in window.
- `git log --all --since="<start>" --until="<end>" --format="%H %ad %s" --date=short | grep -iE "revert|rip|strip|drop|remove|undo|abandon"` — rework signals.
- `grep -rl "<keywords>" "${TICKETS_DIR:-$HOME/.claude/tickets}" --include='*.md'` then read matches — the local ticket tree (source of truth) for briefs at every stage (done, cancelled, backlog, in-progress).

Gracefully skip any source that's unavailable (no `gh` auth, no ticket tree, no git history). Note what was skipped.

## §3. Analysis

Compute from raw data. Don't infer what you can count.

### 3a. PR stats

Compute: total matched, merged, abandoned (closed-not-merged), still open, abandon rate,
median time-to-merge, total lines changed.

### 3b. Timeline phases

Group PRs by week or natural cluster (gaps > 5 days = phase boundary). Name each phase by its dominant theme — derive from PR titles and commit messages, not vibes.

### 3c. Architectural pivots

Identify abandon→replace chains: a PR that closes without merge, followed within 2 weeks by a new PR covering the same area with a different approach. Each chain = a "what went wrong" candidate. Name the pivot: "Abandoned X, replaced with Y."

### 3d. Rework signals

List every commit or PR matching the rework grep from §2. Cluster by affected area. High-density clusters signal a design that needed iteration.

### 3e. Mega PR detection

Flag any PR with:
- >1000 lines changed, OR
- >3 ticket IDs in title or body.

These are scope-creep or "we got scared to split this" signals.

### 3f. Author distribution

Group branches by prefix convention (e.g., `agent/`, `feature/`, `henry/`, `fix/`). Assignee data isn't available locally (no Linear read path) — derive ownership from branch prefix + commit author.

## §4. Draft retro

Structure per `~/.claude/docs/retro-template.md` — that file is the contract (sections,
evidence rules, tone).

Present the draft to the user. **Stop. Wait for feedback before publishing.**

## §5. Publish to Notion

After user explicitly approves (or says "ship it", "looks good", "go"):

1. `mcp__notion__notion-search` for "Retrospectives" under Engineering — get the page ID.
2. `mcp__notion__notion-create-pages` as child of the Retrospectives page:
   - Title: `Retro: <Integration Name> — <YYYY-MM-DD>`
   - Icon: "🔄"
   - Body: the approved retro content, structured as Notion blocks.
3. Report the Notion URL.

If Notion MCP is unavailable, warn once and offer to write the retro to a local markdown file at `~/Documents/retros/<name>-<date>.md` instead.

## §6. Save to memory

After publishing, save a reference so future planning runs can find this:

```
Retro: <Integration Name>
Date:  <YYYY-MM-DD>
Notion: <url>
Key pivots: <1-2 sentence summary>
```

Write to `~/.claude/retros/<slugified-name>.md` (create `retros/` dir if needed). Note in the terminal: "Saved reference at ~/.claude/retros/<file>."

## Stop conditions

- §1: scope ambiguous → ask, stop, wait for answers.
- §4: after presenting draft → stop. Do not publish without explicit approval.
- Never auto-publish. Never skip the §4 draft review.
- If Notion MCP is missing: warn once, continue with available sources, offer fallback at §5.
