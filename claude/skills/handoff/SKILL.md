---
name: handoff
description: Compact the current conversation into a handoff document for another agent to pick up.
argument-hint: "What will the next session be used for?"
---

Write a handoff document summarising the current conversation so a fresh agent can continue the work.

Save it to `~/.claude/handoffs/<UTC-date>-<slug>.md`:
- `<UTC-date>` is `date -u +%Y-%m-%d-%H%M` — keeps the directory sortable.
- `<slug>` is a short kebab-case descriptor of the work, derived from the arguments if
  passed, else from the conversation topic.
- `mkdir -p ~/.claude/handoffs` first; read the file path before writing to it.

After writing the doc, **always** auto-prune spent handoffs so the directory does not grow
unbounded (nothing else ever deletes them — `/resume` and the wt-lanes runner only read):

```bash
find ~/.claude/handoffs -maxdepth 1 -name '*.md' -mtime +"${HANDOFF_RETENTION_DAYS:-14}" -delete
```

Run it every time, after the new doc is on disk — the just-written doc is far younger than the
window so it is never caught. A lane consumes its handoff within minutes of the respawn, so a
doc older than the window is provably spent; deleting it cannot strand an in-flight `/resume`.
Override the window with `HANDOFF_RETENTION_DAYS` (default 14).

This directory is durable and survives `/clear` — the companion `/resume` command reads
the most recent handoff (or one matched by description) to pick the thread back up.

Suggest the skills to be used, if any, by the next session.

Do not duplicate content already captured in other artifacts (PRDs, plans, ADRs, issues, commits, diffs). Reference them by path or URL instead.

If the user passed arguments, treat them as a description of what the next session will focus on and tailor the doc accordingly.

When done, print the saved path so the user can `/resume` it.
