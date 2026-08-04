---
name: tdd
description: 'Red-green-refactor TDD loop. Trigger: TDD/"red-green-refactor"/"test-first"/integration tests/build feature w/ tests.'
---

# Test-Driven Development

## Philosophy

**Core principle**: Tests should verify behavior through public interfaces, not implementation details. Code can change entirely; tests shouldn't. This is *Design to Test* (PP §48) — if a unit is hard to test through its public surface, the unit (not the test) is wrong.

Tracer bullets (PP §15) drive the loop: one thin end-to-end slice (red→green→refactor) before the next. Never horizontal — never "write all tests, then all impl." Each cycle's test responds to what the previous cycle taught you.

Tests are state coverage (PP §65), not code coverage. 100% lines hit means nothing if you only ran one path through them. Drive on what the system *does*, branch by branch.

Good tests exercise real code paths through public APIs and read like a specification;
bad tests mock internal collaborators or break on refactors that didn't change behavior.
Examples: [tests.md](tests.md); mocking guidelines: [mocking.md](mocking.md).

Writing all tests first, then all implementation ("horizontal slicing") produces tests of
*imagined* behavior — bulk-written tests verify shape, not behavior, and go insensitive to
real changes. Always vertical: `test1→impl1, test2→impl2, …` — never
`test1..test5, impl1..impl5`.

## Workflow

### 1. Planning

Use the project's domain glossary so test names and interface vocabulary match the
project's language; respect ADRs in the area you're touching. Design the public interface
first ([deep modules](deep-modules.md), [testability](interface-design.md)) and list the
behaviors to test — not implementation steps.

**You can't test everything.** Focus on critical paths and complex logic. Scale the
ceremony to the change: for non-trivial interface decisions or when behavior priorities
are genuinely ambiguous, confirm the plan with the user; for a small well-understood
change, just state the plan and proceed. (In an autonomous lane the brief is the
confirmation — don't block on a human.)

### 2. Tracer Bullet

Write ONE test that confirms ONE thing about the system:

```
RED:   Write test for first behavior → test fails
GREEN: Write minimal code to pass → test passes
```

This is your tracer bullet - proves the path works end-to-end.

### 3. Incremental Loop

For each remaining behavior:

```
RED:   Write next test → fails
GREEN: Minimal code to pass → passes
```

Rules:

- One test at a time
- Only enough code to pass current test
- Don't anticipate future tests
- Keep tests focused on observable behavior
- **No full-file re-reads between cycles.** The test file and the unit under test are already in context from the previous cycle; your own Edit results show the current state. Locate symbols with grep; when you must re-read, use `offset`/`limit` on the edited range only. (14d audit: test files fully re-read 10–13× per session inside TDD loops — pure cache burn.)

### 4. Refactor

After all tests pass, look for [refactor candidates](refactoring.md):

- [ ] Extract duplication
- [ ] Deepen modules (move complexity behind simple interfaces)
- [ ] Apply SOLID principles where natural
- [ ] Consider what new code reveals about existing code
- [ ] Run tests after each refactor step

**Never refactor while RED.** Get to GREEN first.
