---
description: Explain code flow / call chain / where defined. Wraps Agent(Explore) + org preamble.
argument-hint: <free-text question> — e.g. "how does Wilson V3 dispatch tool calls" or "where is the Pipedream connection ID looked up for Shopify"
---

# /explain-flow $ARGUMENTS

Codebase-explanation wrapper. The user asks "how does X work" / "where is Y wired" / "what calls Z" — this dispatches an Explore subagent with the org preamble prepended, so the answer comes back in project vocabulary with file:line citations.

Use for: data flow, call graph, "what hooks into this", "why does X happen when Y", "where is the source of truth for Z". **Not** for: implementation, refactors, bug fixes — those go to `/scope` or direct work.

## 0. Parse

`$ARGUMENTS` = the question.

- Empty → infer from last few turns of conversation; summarise interpretation in one sentence; if no signal, ask for a question and stop.
- Trivially answerable from already-loaded context (a file already read this turn) → answer directly, do **not** spawn. Note that you did so.

## 1. Detect org preamble

Working directory determines org. Resolve `<org>` from git remote / cwd → `~/.claude/org/<org>/preamble.md`. Read it once. Unknown org or file missing → proceed without, note the gap in the dispatch.

## 2. Dispatch Explore

Single `Agent` tool call, **foreground** (the user wants the answer in-conversation), `subagent_type: Explore`.

Prompt structure:

```
<preamble.md verbatim>

---

Codebase question (research only — no edits, no plan, no implementation):

<the question>

Research budget: medium — search across likely layers (router, workflow, service, model, prompt/skill, trigger task). If the answer is one file, return it fast.

Return format:
1. **Direct answer** in 2–4 sentences.
2. **Call chain / data flow**, each step `file:line` annotated.
3. **Gotchas / branch points** worth knowing (auth boundary, retry, fallback, fan-out).
4. **Open questions** — anything the code did not answer clearly.

Cite file:line for every claim. No speculation. If something is genuinely unclear, say so under (4) instead of guessing.
```

description for the Agent call: `Codebase flow: <≤6-word summary of question>`.

## 3. Relay

When Explore returns, relay the answer to the user verbatim (or near-verbatim — trim only obvious filler). Do **not** restate, summarise, or add commentary unless the user asks a follow-up. The Explore output is the product.

If Explore came back thin (no file:line cites, vague) → re-dispatch once with `Research budget: very thorough` and the same question. Second thin result → surface what was found, flag the gap, stop.

## 4. Stop

No code edits. No ticket creation. No follow-up Agent calls beyond the one re-dispatch in §3. The user chains `/scope` or direct work themselves if the explanation prompts action.
