---
name: grill-with-docs
description: 'Interview loop that stress-tests a plan/design against the domain model — sharpens terms, updates CONTEXT.md/ADRs inline. Trigger: "stress-test this plan", "poke holes in this", "challenge my design", "grill me", "is this approach right", or as /scope''s clarification engine.'
---

<what-to-do>

Interview me about every aspect of this plan until the open decisions are resolved and no fuzzy terms remain — then stop; don't keep grilling past shared understanding. Walk down each branch of the design tree, resolving dependencies between decisions one-by-one. For each question, provide your recommended answer.

Ask the questions one at a time, waiting for feedback on each question before continuing.

If a question can be answered by exploring the codebase, explore the codebase instead.

For any structural decision (data model, layer boundary, vendor adapter, error-propagation strategy), apply **Design it twice** (POSD §11): sketch ≥2 alternatives before agreeing on one. Even when the answer feels obvious, force a second sketch — first instinct is rarely best for hard problems.

Abstractions outlast details (PP §53). When pinning a term, capture the *concept* in the glossary, not its current implementation. The implementation will move; the concept (Order, Customer, Shipment) is the durable surface.

Project glossary (PP §54) is the durable artifact of this interview — `CONTEXT.md` is the doc, this skill is the editor. Conflicting term → resolve now, write back inline.

</what-to-do>

<supporting-info>

## Domain awareness

During codebase exploration, also look for existing documentation:

### File structure

Single context (most repos): `CONTEXT.md` + `docs/adr/` at the root. A `CONTEXT-MAP.md` at
the root means multiple contexts, each with its own `CONTEXT.md` + `docs/adr/` — full
layout + inference rules: [CONTEXT-FORMAT.md](./CONTEXT-FORMAT.md).

Create files lazily — only when you have something to write. If no `CONTEXT.md` exists, create one when the first term is resolved. If no `docs/adr/` exists, create it when the first ADR is needed.

## During the session

### Challenge against the glossary

When the user uses a term that conflicts with the existing language in `CONTEXT.md`, call it out immediately. "Your glossary defines 'cancellation' as X, but you seem to mean Y — which is it?"

### Sharpen fuzzy language

When the user uses vague or overloaded terms, propose a precise canonical term. "You're saying 'account' — do you mean the Customer or the User? Those are different things."

### Discuss concrete scenarios

When domain relationships are being discussed, stress-test them with specific scenarios. Invent scenarios that probe edge cases and force the user to be precise about the boundaries between concepts.

### Cross-reference with code

When the user states how something works, check whether the code agrees. If you find a contradiction, surface it: "Your code cancels entire Orders, but you just said partial cancellation is possible — which is right?"

### Update CONTEXT.md inline

When a term is resolved, update `CONTEXT.md` right there. Don't batch these up — capture them as they happen. Use the format in [CONTEXT-FORMAT.md](./CONTEXT-FORMAT.md).

`CONTEXT.md` should be totally devoid of implementation details. Do not treat `CONTEXT.md` as a spec, a scratch pad, or a repository for implementation decisions. It is a glossary and nothing else.

### Offer ADRs sparingly

Only offer an ADR when the decision passes the three-part gate in
[ADR-FORMAT.md](./ADR-FORMAT.md) (hard to reverse + surprising without context + a real
trade-off) — any one missing, skip it.

</supporting-info>
