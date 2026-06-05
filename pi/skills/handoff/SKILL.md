---
name: handoff
description: Compact the current conversation into a handoff document for another agent to pick up.
argument-hint: "What will the next session be used for?"
---

Write a handoff document summarising the current conversation so a fresh agent can continue the work.

Save it to `~/.pi/agent/handoffs/<UTC-date>-<slug>.md`:
- `<UTC-date>` is `date -u +%Y-%m-%d-%H%M` — keeps the directory sortable.
- `<slug>` is a short kebab-case descriptor of the work, derived from the arguments if
  passed, else from the conversation topic.
- `mkdir -p ~/.pi/agent/handoffs` first; read the file path before writing to it.

This directory is durable across Pi sessions — the companion `/resume` command reads
the most recent handoff (or one matched by description) to pick the thread back up.

Suggest the skills to be used, if any, by the next session.

Do not duplicate content already captured in other artifacts (PRDs, plans, ADRs, issues, commits, diffs). Reference them by path or URL instead.

If the user passed arguments, treat them as a description of what the next session will focus on and tailor the doc accordingly.

When done, print the saved path so the user can `/resume` it.
