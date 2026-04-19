---
description: Review recently changed code for reuse, clarity, and efficiency, then fix what you find.
---

# /simplify

Review the **recently modified** code in this session for issues, then fix them in place. Do not expand scope to unmodified code unless the user asks.

## Scope

- Default: the current `git diff` (unstaged + staged), or the diff of the current branch vs. main if mid-feature.
- Ignore unchanged files unless the user explicitly names one.

## What to look for

1. **Reuse** — is there an existing helper / primitive / util that the new code should be using instead of a locally reinvented version?
2. **Clarity** — are names specific (`fetchUserProfile` not `getData`)? Are guard clauses up top, happy path at shallowest indent? Is there a boolean with a fuzzy name that should be `isX` / `hasY`?
3. **Efficiency** — redundant work (double iteration, re-fetching in a loop, unnecessary awaits, synchronous sleeps)? Tight loops allocating in the hot path?
4. **Over-abstraction** — premature helpers for a single caller, interfaces for one implementation, options objects with one field. Three similar lines is fine; a wrapper over one caller is not.
5. **Dead / defensive code** — validation for conditions that can't happen, fallbacks for states that don't exist, error handling that silently swallows.
6. **Comments that describe the what** — delete. Keep only comments that explain a non-obvious why (hidden constraint, workaround, subtle invariant).
7. **Inconsistencies with the surrounding code** — a new file that doesn't match the repo's pattern for similar files.

## Output

For each issue:
1. Quote the file:line.
2. One-sentence description of the problem.
3. The fix (applied directly via Edit).

At the end: a one-paragraph summary of what changed and why. If nothing needs fixing, say so explicitly — don't invent issues.

## Principles (from global CLAUDE.md)

- Guard clauses at top, early return, max 2 indent levels.
- One task per function.
- Specific names. No `tmp`, `data`, `result`.
- `const` by default.
- Composition over inheritance. Narrow interfaces.
- Comment the why, never the what.

Reference: OV `resources/agents/code-structure-reference` has the long-form principles with examples.
