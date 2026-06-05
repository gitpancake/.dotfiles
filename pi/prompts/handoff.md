---
description: Write a compact handoff for another agent or future session
argument-hint: [handoff goal]
---
Create a handoff for: $ARGUMENTS

Write it to `~/.pi/agent/handoffs/<UTC>-<slug>.md` unless the user asks for chat-only. Create the directory if needed.

Summarize only durable, actionable context:
- goal and current status
- decisions made
- files touched or inspected
- exact commands run and results
- remaining work
- blockers / risks
- recommended next command

If a handoff skill is available, load it and follow it, but prefer the Pi handoff path above over legacy harness paths. Otherwise produce markdown and save it to the Pi handoff directory.
