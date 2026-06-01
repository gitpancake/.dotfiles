---
description: Review current git diff like a senior engineer
argument-hint: [focus]
---
Review the current git diff. If $ARGUMENTS is non-empty, use it as the review focus: $ARGUMENTS

Check:
- correctness bugs and edge cases
- security, auth, tenant isolation, and secret leakage
- error handling and silent catches
- tests / verification gaps
- accidental broad or unrelated changes
- violations of repo AGENTS.md / CLAUDE.md instructions

Read the relevant files before judging. Report blocking issues first with file paths. If there are no blockers, say so and list non-blocking suggestions separately.
