---
description: Fetch a Linear ticket and render it in the terminal so user can read it without leaving tmux.
argument-hint: <LINEAR-ID>
---

# /read-ticket $ARGUMENTS

Pure read. No edits. No Linear comments. No `/ticket-pickup` follow-on. Just print the ticket so user can review it before deciding what to do next (`/rescope`, `/ticket-pickup`, or close it out).

If `$ARGUMENTS` is empty, ask for a Linear ID and stop.

## 1. Fetch (parallel)

- `mcp__linear-server__get_issue $ARGUMENTS` — body, status, assignee, priority, labels, project, parent, sub-issues, attachments.
- For each linked sub-issue or parent surfaced in the body, fetch its title + status (don't fetch full bodies — keep it cheap).
- `gh pr list --search "$ARGUMENTS" --state all --json number,title,state,url 2>/dev/null` — any PRs referencing this ticket.
- `git log --all --oneline --grep="$ARGUMENTS" 2>/dev/null | head -10` — has a branch already started?

## 2. Render — terse, terminal-friendly

```
[$ARGUMENTS] <Title>
status: <state>     priority: <p>     assignee: <name or unassigned>
project: <name>     labels: <a, b, c>
parent: <ID title> (status)             # only if present
url: <linear url>

— body —
<verbatim, markdown intact>

— sub-issues —
<ID> <title> [status]                   # one per line, only if present

— recent comments (last 3) —
<author> · <relative time>
  <verbatim>

— links —
PRs:        <#N url state> | "—"
Branches:   <name> | "—"
Attachments: <titles, comma-separated> | "—"
```

Trim long bodies if needed but never paraphrase. Whole point is user reads the source.

## 3. Stop

After rendering, say one line: `Ready. /rescope or /ticket-pickup next.`

No suggestions, no summaries, no "should we...". The whole command is read-only.
