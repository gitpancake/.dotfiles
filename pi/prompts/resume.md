---
description: Resume from a handoff doc in the current Pi session.
argument-hint: "[--slim|--full] [handoff description]"
---

# /resume $ARGUMENTS

Resume from a handoff in this Pi session. Do not start external workers or child agents. Continue inline.

## Parse

- `--slim`: read handoff + one `git status`/branch check only.
- `--full`: follow referenced files/PRs/commits as needed before acting.
- No flag: auto. If handoff has >=80 lines, use slim; otherwise full.
- Remaining text is a case-insensitive filename/slug match.

## Find handoff

Use `ls -t ~/.pi/agent/handoffs/*.md 2>/dev/null`.

- None: report no handoffs and stop.
- No description: use latest.
- Description: match filename substring.
  - One match: use it.
  - Multiple: list matches and ask which.
  - None: use latest and explicitly say no match was found.

## Read and orient

Read the chosen handoff in full.

Slim mode:
- Run one `git status --short --branch` in cwd.
- Trust the handoff unless contradicted by git state.
- Do not prefetch every referenced artifact.

Full mode:
- Verify referenced briefs/plans/commits/PRs only as needed to make the next step safe.
- Surface stale or missing anchors instead of guessing.

## Continue

Say two lines max:

`Resumed from <file> (<mode>).`
`Next: <concrete next step>.`

Then continue the work using Pi tools. Load suggested skills only if they match the next action.
