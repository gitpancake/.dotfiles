# Design Principles

Reference for tags cited across slash commands / agents / skills. Sources: **POSD** = *A Philosophy of Software Design* (Ousterhout, 2nd ed). **PP** = *The Pragmatic Programmer* (Hunt/Thomas, 1st ed). Tag form: `POSD §<chapter>` / `PP §<tip-number>`.

**Reducing complexity beats any single rule.** If the rule and the goal conflict, the goal wins — but say so.

## Modules + Layers

- **Deep modules** (POSD §4). Simple interface, rich implementation. Cost = interface size; benefit = functionality. Maximize ratio. Shallow class w/ wide API = anti-pattern.
- **Hide info, don't leak it** (POSD §5). One design decision lives in one module. Same knowledge in two places → couple by encapsulation, not by convention. `private` keyword ≠ hiding.
- **Different layer, different abstraction** (POSD §7). Pass-through methods (`foo()` that just calls `bar()`) + pass-through variables (arg threaded 3+ layers untouched) = shallow + coupling. Eliminate or redistribute responsibility. Each layer translates to its own shape — DB row ≠ domain object ≠ API DTO ≠ view model.
- **Pull complexity downward** (POSD §8). Module owner eats the hard problem; callers get the simple call. Don't punt config knobs upward "for flexibility."
- **General-purpose modules are deeper** (POSD §6). Same module, fewer methods, broader use. Special-purpose interfaces multiply.
- **Decouple — Demeter** (PP §36). Function talks only to: itself, its params, things it constructed, direct components. `a.b.c.d()` chains = refactor signal.
- **Orthogonality** (PP §13). Unrelated things change independently. Schema change shouldn't ripple into a UI test.

## Errors + Contracts

- **Design by contract** (PP §31). Every exposed method has a named precondition + postcondition. State in the type signature where possible, one-line comment otherwise.
- **Crash early** (PP §32). The instant an invariant breaks, throw — don't propagate corrupt state. `if (!shipment.id) throw …` beats `?.` chained downstream.
- **Assertions ensure can't-happen** (PP §33). When an assertion fires, the model is wrong — not the data. Use assertions for impossible, exceptions for exceptional.
- **Define errors out of existence** (POSD §10). Reduce *places* exceptions must be handled, not handler counts. Mask at the lowest layer that can. Don't punt error to caller when you can make it impossible.
- **Use exceptions for exceptional problems** (PP §34). Don't use exceptions for normal control flow.

## Process

- **Tracer bullets, not horizontal slices** (PP §15). One thin end-to-end slice → next slice. Never "write all tests, then all impl" or "build whole schema layer first." Each cycle responds to what the previous taught you.
- **Design it twice** (POSD §11). For any structural choice, sketch ≥2 alternatives. Even when first feels obvious — force a second sketch. First instinct rarely best for hard problems.
- **No final decisions / reversibility** (PP §14). Architectural choices that lock the project in → ADR + alternatives + explicit cost. Vendor + DB choices especially.
- **Don't program by coincidence** (PP §44). If you don't know *why* it works, it doesn't work — it's pending. No "this seems to fix it, ship it." Name the contract or assert it.
- **Refactor early, refactor often** (PP §47). Refactoring is part of the change, not a follow-up. Boy-scout rule applies inside scope.
- **Don't live with broken windows** (PP §4). Bad pattern adjacent to your change → fix or ticket. Don't normalise rot.
- **DRY** (PP §11). Every piece of *knowledge* has one canonical representation. Same shape ≠ duplication; same *meaning* is.
- **Configure, don't integrate** (PP §37). New knob → config / metadata. Don't fork code path for every flavour.

## Debugging

- **Don't panic** (PP §25). Deadline pressure produces speculative fixes. Slow down.
- **"select" isn't broken** (PP §26). OS / framework / std lib is almost never the bug. Suspect your code first. Hoofprints → horses, not zebras.
- **Don't assume — prove it** (PP §27). Every hypothesis ships with the probe that would falsify it. Hypotheses are falsifiable or they're vibes.
- **Fix the problem, not the blame** (PP §24). Whose code broke it is irrelevant to fixing it.
- **Find bugs once** (PP §66). Every fix ships with a regression test AND a grep for sibling occurrences. Bug-classes survive because nobody looked for peers.

## Testing

- **Design to test** (PP §48). If a unit is hard to test through its public surface, the unit (not the test) is wrong.
- **Test state coverage, not code coverage** (PP §65). 100% lines hit means nothing if you only ran one path through them.
- **Coding ain't done 'til all tests run** (PP §63). Type-check is not evidence; an exercised feature is.

## Domain + Naming

- **Stay close to the problem domain** (PP §17, §53). Code uses domain vocabulary; abstractions outlive details. Glossary in `CONTEXT.md` is load-bearing.
- **Project glossary** (PP §54). Term conflicts → resolve and write back inline.
- **Code must be obvious** (POSD §18). Reader-time > writer-time. Nonobvious code = bugs.
- **Names should be precise + consistent** (POSD §14). Generic name = red flag. `fetchUserProfile` not `getData`; `delayMs` not `delay`.
- **Consistency** (POSD §17). Similar things done similar ways. Reading one place predicts another. Don't change convention without reason.

## Design Patterns

Source: **GoF** = the Gang of Four catalog as written up at refactoring.guru/design-patterns/catalog. Tag form: `GoF:<Pattern>`. Name the pattern only by its **force** — the thing that varies, arrives, or must be hidden. No force → no pattern → plain function.

**A pattern must pay for itself.** It earns its place when it removes a named smell at ≥2 sites or gives the next variant a home that needs no edit to the existing ones. "Could use a pattern" is decoration. A pattern the reader has to look up loses to code they can read. This is a TypeScript codebase: most GoF class diagrams collapse to a function type, a discriminated union, or a record keyed by variant — reach for that shape first.

### Creational

- **Factory Method** — construction varies by kind, callers must not know which. Shape: `create<Thing>({ kind, … })` returning the interface; a `Record<Kind, Ctor>` beats a subclass tree. Force: ≥2 kinds today, not "someday".
- **Abstract Factory** — a *family* of things must match (carrier client + rate parser + label renderer). Shape: one object with the family's fns. Rare; one mismatched family is the signal.
- **Builder** — construction has stages with ordering rules or many optional parts. Shape: a chained builder or staged fns. Force: telescoping params that an object param (house rule) can't fix because order matters.
- **Prototype** — new instance from an existing one. Shape: spread / `structuredClone`; never a `clone()` class method.
- **Singleton** — one instance, global access. Shape: a module-scope `const`. Never a class with `getInstance`; hidden global state is the smell this pattern usually *causes*.

### Structural

- **Adapter** — an interface we don't own must fit one we do (`freightProvider/` is the standing example). Shape: one fn or object per vendor mapping their shape to ours. Force: the foreign shape is fixed.
- **Bridge** — two axes vary independently (document type × render target). Shape: abstraction holds an implementation interface. Force: N×M classes otherwise.
- **Composite** — tree of parts and wholes handled uniformly (nested address-book groups). Shape: recursive union type + one walk fn.
- **Decorator** — add behavior around an unchanged core (retry, logging, caching around a service call). Shape: `withRetry(fn)` higher-order fn. Force: the core must not learn about the wrapper.
- **Facade** — one call hides a subsystem's choreography. Shape: a use case. This is what a use case behind its ports already is; a new facade over one is a pass-through (POSD §7).
- **Flyweight** — many instances share heavy intrinsic state. Rare here; measure first (POSD §20).
- **Proxy** — control access to a thing: lazy, cached, guarded. Shape: same interface, wrapping fn. Distinguish from Decorator by intent: Proxy gates, Decorator adds.

### Behavioral

- **Chain of Responsibility** — an ordered set of handlers, first match wins or each may pass (referee rules, ingress guardrails). Shape: array of `(input) => Verdict | undefined`, one loop.
- **Command** — an action reified as data: queued, logged, undone, replayed (async tasks, activityLog entries). Shape: a discriminated union + one dispatcher.
- **Iterator** — sequence traversal decoupled from storage. Shape: generator / `AsyncIterable`. Force: paging, streaming.
- **Mediator** — N components talk through one hub instead of N². Force: a web of cross-references. A workflow is usually the mediator already.
- **Memento** — snapshot + restore without exposing internals (checkpoints, handoffs). Shape: immutable snapshot value; the owner alone reads it back.
- **Observer** — one event, many listeners that the emitter must not know (webhook fan-out, deadline events). Shape: typed emitter or a task per subscriber. Force: subscribers change without touching the emitter.
- **State** — behavior differs by a lifecycle state that transitions (shipment status, task status). Shape: `Record<State, Handlers>` + one transition table. Force: the same `switch (state)` at ≥2 sites.
- **Strategy** — one operation, interchangeable algorithms chosen at runtime (rate selection, dedupe policy). Shape: fn type + `Record<Kind, Strategy>`. Force: the same `if (kind === …)` ladder at ≥2 sites. One variant → a function, not a Strategy.
- **Template Method** — fixed skeleton, variable steps. Prefer Strategy or composition: pass the steps in. Inheritance-based template = anti-pattern here (composition > inheritance).
- **Visitor** — new operations over a closed set of node types. Shape: discriminated union + exhaustive `switch` with `satisfies never`. Force: the node set is closed and the operation set grows.

### Smell → move

Canonical refactoring.guru smell names; cite them in briefs, reviews, and audits.

- **Switch on type** repeated across sites → Strategy / State / Visitor (which one: does the variant *do* something, *transition*, or get *operated on*?).
- **Telescoping params / long parameter list** → object param (house rule); ordering rules → Builder.
- **Shotgun surgery** (one change, many files) → a decision is leaking; hide it in one module (POSD §5).
- **Divergent change** (one file, many reasons to change) → split by reason.
- **Feature envy** → move the fn to the data it reads.
- **Middle man** → inline the pass-through (POSD §7).
- **Primitive obsession** → branded type or small value object; parse once at the boundary (Zod).
- **Speculative generality** → delete the unused extension point; a pattern with one variant is this smell.
- **Comments** → the code failed to say it; rename or extract until the comment is redundant, then delete it (POSD §13).

## Comments

- **No code comments for what** (POSD §13). Names + structure carry intent. Keep only non-obvious *why* — hidden constraint, workaround, subtle invariant.
- **Comments near code** (POSD §16). Update during diff; postmortems in commit log, not source.

## How to cite

In slash command / agent / skill docs, cite the principle by tag when justifying a rule:

> Pass-through props (POSD §7) signal the wrong owner. Lift state.

In PR / commit messages when arguing scope:

> Pulling validation out of the route into the service per POSD §8 — caller simplified, error count reduced per POSD §10.

In code review when redirecting:

> This violates PP §44 (programming by coincidence) — please name the invariant before merging.

The point isn't bookishness; it's making rules arguable. "Should we?" → cite tag + reason → discuss.

## Out of scope for this reference

Some book themes are about the human or the team, not the code:
- Care / craft / portfolio (PP §1, §8) — human discipline.
- Estimating (PP §13, §18) — calendar work.
- Pragmatic teams / automation culture (PP §41, §42, §61) — team practice.
- Designing for performance (POSD §20) — workload-specific; "measure first" is the only general rule.
