# Global Instructions

## Programming Practices

Apply these when writing, reviewing, or refactoring code. These complement (not replace) the built-in coding guidelines — focus here is on principles the defaults don't cover.

### Readability
- Minimize time-to-understanding. A stranger should follow the logic without verbal explanation.
- Specific names, not generic (`delayMs` not `delay`, `isValid` not `flag`). Attach units. For ranges: `first`/`last` (inclusive) or `begin`/`end` (exclusive).
- Guard clauses and early returns. Edge cases at the top, happy path at shallowest indentation — max 2 levels deep.
- Explaining variables for complex conditions: `const isOwner = req.user.id === doc.ownerId;` then `if (isOwner || isAdmin)`.
- When boolean logic tangles, consider the negation — "when does this NOT hold?" often has fewer cases.
- Comment the "why" (tradeoffs, non-obvious decisions), never the "what."

### Design
- Composition over inheritance. Inherit only when is-a genuinely holds (Liskov).
- High cohesion + low coupling. Avoid control coupling (passing flags that dictate behavior — use polymorphism).
- Layer architecture: higher layers call lower layers, never the reverse.
- Apply patterns (Observer, Factory, Facade, Adapter) where they simplify — never force one where a plain function works.

### Algorithms & Data Structures
- Model before coding. Many problems are graph problems in disguise.
- Map to known patterns: BFS (min steps), Dijkstra (weighted paths), DP (optimal-over-sequence), greedy (intervals), binary search (monotonic boundaries), union-find (grouping).
- Choose structures by access pattern: hash map (O(1) lookup), heap (min/max), sorted structure (range queries), stack (nesting), queue (levels).
- Brute force first for correctness, then optimize. State complexity explicitly.

### Systems & Concurrency
- Consistent lock ordering to prevent deadlocks. Prefer immutability to eliminate races entirely.
- Pool expensive resources (threads, connections). Apply backpressure when overloaded — reject or slow intake rather than thrashing.
- Exploit locality (temporal and spatial) in data access — this underlies caches, pools, indexes, and buffer strategies.

### Networking
- Choose protocols by latency/loss/ordering needs, not "TCP for everything."
- Minimize connection overhead: persistent connections, pooling, multiplexing (HTTP/2, gRPC).
- Exponential backoff with jitter for retries. Aggressive retries cause congestion collapse.

### Error Handling
- Fail fast at system boundaries (user input, external APIs, config). Let invalid state crash early with clear messages.
- Inside trusted internal code, trust the types and framework guarantees — don't defensively check for impossible states.
- When crossing engine/service boundaries, wrap in try/catch for graceful degradation — one failing dependency shouldn't take down the caller.
- Errors should be actionable: include what failed, why, and what to do about it. No silent swallowing.

## Git Workflow

- **Auto-commit** after completing an isolated chunk of work (feature, bugfix, refactor)
- **Never push** unless explicitly asked ("push", "push to upstream", "deploy")

## Project Documentation Maintenance

After each chunk of work:
- **Update project `CLAUDE.md`** with new conventions, architecture decisions, setup steps, gotchas, or non-obvious context. This is the primary session-to-session knowledge store.
- **Update `README.md`** if changes affect user-facing behavior, setup, API surface, or structure. Skip for internal refactors.

Keep updates concise and incremental. Only update docs for the project you're actively working in.

## OpenViking — cross-project knowledge base

Persistent vector-indexed knowledge base (MCP) for knowledge that **spans projects or lives outside any single repo** — external API docs, cross-project decisions, research, reference material.

**Not for:** per-project context (CLAUDE.md), work summaries (git), user preferences (auto-memory), anything derivable from code.

### MANDATORY: Check OV before fetching external docs

**Before `WebFetch`, `WebSearch`, or `context7` for API docs, ALWAYS `find`/`search` OpenViking first.** Re-fetching wastes time and context. If OV has it, use it. If not and you fetch externally, store it with `add_resource` for next time.

### Known resource index

| Topic | OV path |
|-------|---------|
| Gmail API | `resources/life-os/external-apis/gmail-api` |
| Google Calendar API | `resources/life-os/external-apis/google-calendar-api` |
| GCP Pub/Sub | `resources/life-os/external-apis/gcp-pubsub` |
| Open-Meteo | `resources/life-os/external-apis/open-meteo` |
| Anthropic Claude API | `resources/life-os/external-apis/anthropic-claude-api` |
| Anthropic Models | `resources/life-os/external-apis/anthropic-models` |
| football-data.org v4 | `resources/life-os/external-apis/football-data-v4` |
| Neynar / Farcaster API | `resources/life-os/external-apis/farcaster-neynar-api` |
| Farcaster Hub (direct) | `resources/farcaster-hub-direct-casting` |
| RS3 Hiscores / CML | `resources/rs3-hiscores-api` |
| GCP Pub/Sub infra | `resources/life-os/gcp-pubsub` |
| UI design system | `resources/life-os/ui-design-system` |
| OpenSea API | `resources/opensea-api` |
| Art Blocks API | `resources/art-blocks-api` |
| Gondi SDK / docs | `resources/gondi` |
| Raster.art | `resources/raster-art-research` |

Table may be stale — run `ls` on the relevant `resources/` path when in doubt.

### When to READ

Beyond the mandatory doc-check: search OV when the user asks about cross-project patterns, when starting work that touches multiple projects, or when the user references a service/API by name.

### When to WRITE

Store: external API docs fetched during a session, cross-project architectural decisions, anything the user explicitly asks to save.
Don't store: work summaries, per-project conventions, ephemeral debugging context.

### Hygiene
- Remove or update outdated entries when you encounter them
- Descriptive directory names (`resources/opensea-api/`, not `resources/Document_1/`)
- Fewer high-quality entries over many low-value ones
