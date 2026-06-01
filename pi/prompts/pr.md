---
description: Prepare a PR body from the current branch
argument-hint: [extra context]
---
Prepare a PR for the current branch. Do not push or create the PR unless I explicitly ask.

Use the repository PR template if present. Inspect:
- git status --short --branch
- current branch and upstream
- commits versus origin/main
- diff stat and key diffs

Draft concise sections for:
- Thinking Path
- What Changed
- Verification
- Risks
- Model Used
- Checklist

Extra context: $ARGUMENTS
