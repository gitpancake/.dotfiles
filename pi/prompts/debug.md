---
description: Diagnose a bug with reproduce-minimize-fix discipline
argument-hint: <symptom or failure>
---
Debug this issue: $ARGUMENTS

Use the diagnose loop:
1. Read project instructions.
2. Reproduce or gather exact failure evidence.
3. Minimize to the responsible component.
4. Form 1-3 hypotheses and test them with source inspection or commands.
5. Fix the smallest root cause.
6. Add or run a regression check.

Do not guess APIs, paths, or config names. If the evidence is insufficient, ask for the missing artifact instead of inventing.
