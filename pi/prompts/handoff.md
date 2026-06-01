---
description: Write a compact handoff for another agent or future session
argument-hint: [handoff goal]
---
Create a handoff for: $ARGUMENTS

Summarize only durable, actionable context:
- goal and current status
- decisions made
- files touched or inspected
- exact commands run and results
- remaining work
- blockers / risks
- recommended next command

If a handoff skill is available, load it and follow it. Otherwise produce markdown I can paste into the next session.
