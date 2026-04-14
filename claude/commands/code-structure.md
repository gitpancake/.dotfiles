# Code Structure Skill

Apply these principles when writing or reviewing any code. These are non-negotiable structural habits, not suggestions.

## When This Activates
Any time code is being written, refactored, or reviewed — regardless of which agent is active.

## Structural Rules

### Function Shape
- Guard clauses at the top. Edge cases first, early return. Happy path at shallowest indentation.
- Max 2 levels of nesting. If deeper, extract or use guard clauses.
- One task per function. If a function does parsing AND computing AND formatting, split it.
- Functions over ~20 lines likely need a helper extracted.

### Naming
- Specific over generic: `fetchUserProfile` not `getData`, `delayMs` not `delay`.
- Booleans read as assertions: `isValid`, `hasChildren`, `canRetry`.
- Ranges: `first`/`last` (inclusive) or `begin`/`end` (exclusive). Never ambiguous.
- No `tmp`, `data`, `result`, `val`, `info`, `item` unless truly throwaway.

### Code Organization
- Blank line + one-line summary comment between logical sections ("paragraphs").
- Declare variables close to first use. `const` by default, `let` only when mutation needed.
- Complex conditions become named booleans: `const isOwner = req.user.id === doc.ownerId`.
- If boolean logic tangles, check the negation — "when does this NOT hold?" often has fewer cases.

### Abstraction
- Extract unrelated subproblems into helpers. Main function should read like a plan, not implementation details.
- Composition over inheritance. Delegate to composed objects for selective reuse.
- Narrow interfaces — don't pass full objects when a function only needs 2 fields.
- Patterns (Factory, Facade, Adapter, Observer) only where they simplify. A plain function is fine.

### Comments
- Comment the "why" (tradeoffs, non-obvious decisions, edge case reasoning). Never the "what."
- A comment explaining bad code = fix the code instead.

## Deep Reference
Search OV `resources/agents/code-structure-reference` for detailed principles with examples.
