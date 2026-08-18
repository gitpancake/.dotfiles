---
description: Free-text problem → engineered Linear ticket (or project + children). Writes on "go".
argument-hint: <free-text problem statement>
---

# /scope $ARGUMENTS

User's standard ask: "scope this out, ready for engineering." Output is a **Linear issue**
(or, for an epic, a **Linear project + child issues**) whose description a `wt` lane can pick
up without redoing discovery — it carries the surface area, the mirror reference, the
gotchas. Refine the request, don't restate it.

Linear is the source of truth (global CLAUDE.md §Ticket Lifecycle); write via the `linear`
skill (`linear-gql.py`). This command writes to Linear only — plus the one `CONTEXT.md`
docs-commit in §7. Lanes get the brief via `linear-brief.sh` materialization at `/pickup`
time, not from anything /scope leaves on disk.

If `$ARGUMENTS` is empty, infer the problem from conversation context — what was just
discussed, debugged, or decided. Summarize your interpretation in 1–2 sentences and proceed.
No relevant context either → ask for a problem statement and stop.

## 0. Evidence pass — before the grill

The brief's slots (Requirement / Context / Limitations / AC / Proof) get filled from
evidence, not the user's recollection. If the request traces to a meeting, a Slack thread,
or a support ticket — or the user names one — pull it first:

- **Granola** (`granola` skill): the meeting's note + action items.
- **Pocket** (`pocket` skill): the verbatim transcript — the throwaway constraints
  ("oh, and it has to…") live here, not in the summary.
- **Slack** (`cartage-bots` skill): the originating thread. Support-originated → add the
  Plain thread (`plain-api` skill).

Distill an evidence pack:

- Candidate requirements — verbatim quote + speaker.
- Constraints + success criteria mentioned.
- **Explicitly-deferred items** — who deferred, when.
- Contradictions: source vs source, or source vs `$ARGUMENTS`.

No traceable source → skip silently; §1 grills from scratch as before. Never fabricate a
citation — an uncited AC line is honest, a fake quote is not.

PII: transcripts are raw customer conversation. The pack stays cockpit-side; only
distilled quotes reach the Linear body, contact details (emails, phones) stripped.

## 1. Clarify before exploring — grill cadence

If `$ARGUMENTS` is under ~15 words **or** missing any of the below, grill.

**Engine: the `grill-with-docs` skill is /scope's interview loop.** Invoke it here for the
clarification + glossary pass — it owns Design-it-twice cues, `CONTEXT.md` term-pinning, and
domain-vocab discipline. Lanes do not re-grill: this skill is /scope-owned, not lane-owned,
so the brief that ships into `wt` is already sharp.

**Evidence inverts the grill.** When §0 produced a pack, present extractions for
confirm/override instead of interviewing the user's memory:

> Q: Transcript 8/14 — Ben: "needs to work for the Connect channels too." In scope?
> Recommended: yes. Affirm or override.

One Q per candidate requirement, deferred item, and contradiction (batch the
uncontroversial ones). The user validates, they don't recall — this is what catches the
requirement they forgot they agreed to, before it becomes review round 2. The four
standing questions below still apply; ask only the ones the pack doesn't answer.

**One question at a time. Each Q ships w/ your recommended answer.** User affirms → next Q.
User overrides → record + next. Skip what you can already answer from context.

- **Who hits this**: customer / internal user / engineer?
- **End state** in one sentence.
- **Surface area hint**: workflow / vendor / UI / infra / prompt — even rough.
- **Epic or single ticket?**

Format per Q:
> Q: Who hits this?
> Recommended: internal user (you mentioned ops dashboard). Affirm or override.

Walk decision tree — resolve dependencies one branch at a time. Codebase-answerable Q → grep
instead of asking. Stop when above four resolved + no fuzzy terms remain.

## 2. Codebase exploration — the refinement

This is the part that makes the brief pickable rather than a wishlist.

### 2a. Mirror search (before grep)

A lot of work is "mirror an existing integration for a new vendor" shaped. Find
the structural twin first — name it, and for each layer it touches (workflow / route / model
/ UI / task / tool def) name the mirror's entry-point file, path + one-line reason. Vendor
work → check context7 / official docs for the vendor API; cite the doc section used or
note "no docs found."

### 2b. Surface area (grounded grep)

- Top **≤8 files** to start in, each with a one-line reason.
- Imports / callers of the affected types and functions.
- Project `CLAUDE.md` "Gotchas" entries that apply — quote them verbatim.

### 2c. Glossary check

Scan `CONTEXT.md` (root or per-context via `CONTEXT-MAP.md`) for terms in the request. Term
conflicts with existing definition → call out + resolve before drafting. Fuzzy/overloaded
term ("account" = Customer or User?) → propose canonical, get confirmation, update
`CONTEXT.md` inline. No `CONTEXT.md` yet → create lazily only when first term resolves.
Brief must not ship with terms that contradict glossary.

### 2d. Mechanism honesty

Env vars / secrets, external setup (vendor account, webhook, OAuth app), new infra (background
task, endpoint, collection) — list as prerequisites, flag anything unconfirmed. Never invent
paths, symbols, or env vars. "TBD — needs investigation" beats a guess.

### 2e. Design it twice (POSD §11) — only for structural choices

If the brief introduces a structural decision (new data model, new routing-key shape, new
service boundary, vendor adapter, error-propagation strategy) — sketch ≥2 alternatives before
writing the brief. Two bullets each: shape, cost, what it makes easy/hard. Pick one and say
why. **Even when the answer feels obvious, force a second sketch.** First idea is rarely best
for hard problems.

For reversibility (PP §14): if the chosen approach is hard to back out of (DB column we'd
have to migrate off, vendor we'd have to swap, public type shape), add a `## Reversibility`
section. State: what locks us in, what would force a change, rough escape cost. If the choice
deserves an ADR (hard to reverse + surprising + a real trade-off), say so — `/grill-with-docs`
will offer to write it.

Routine choices (which existing helper to call, which existing table to extend) — skip §2e.
Reserve for decisions that survive past the PR.

Apply the org's risk callouts where they fit — `~/.claude/org/<org>/preamble.md`.

## 3. Name it — title, team, shape

- **Title** — `Feature:`/`Fix:`/`Improvement:`/`Refactor:` prefix, action-oriented, derived
  from the end state. Linear adds its own id — never bake one into the title.
- **Team** — per global CLAUDE.md §Linear teams: engineering work → **ENGH**; ops → **AO**;
  agent-behavior/config → **AOA**. Ask only if genuinely ambiguous.
- **Shape** — single issue or epic (project + children), from §1.

Branch/lane slugs derive from the title at `/pickup` time (slug rule: global CLAUDE.md) —
/scope doesn't mint filenames.

## 4. Brief — house style

**Prose style: Write Simply** (paulgraham.com/simply.html). The brief is read by a lane
mid-task and by reviewers months later; reading friction compounds. Short sentences. Plain
words. One idea per sentence. Decode internal shorthand in place ("a tombstone revision,
so history survives"); keep exact technical names (paths, workflows, flags, env vars)
verbatim. Simple words are not less information — every concrete fact the lane needs
(file paths, mirror names, gotcha quotes, prerequisites, citations) stays. Cut only what
doesn't change what gets built. A sentence that needs rereading gets rewritten; a section
with nothing to say gets deleted, not padded. Fancy words that could be plain ones are
clumsy, not precise.

**Single issue** — the house template (global CLAUDE.md §Ticket Lifecycle) plus the two
/scope-only sections, in order:

- `## Requirement` — the user-facing outcome, 2–3 sentences.
- `## Context` — why: the refined problem, mirror reference, decisions from the grill,
  gotchas quoted from project CLAUDE.md.
- `## Surface area` — mirror / ≤8 starting files with one-line reasons / prerequisites +
  unconfirmed mechanisms from §2d. (/scope-only.)
- `## Acceptance Criteria` — checkboxes, each a testable yes/no. Never "works correctly".
- `## Limitations` — out of scope, each item with its why (the why kills scope creep and
  relitigating).
- `## Proof` — defined now, before work starts. **Manual Tests**: concrete steps + the
  evidence each produces. **Automated Tests**: the tests the lane will add. If you can't
  name what would prove it works, the AC aren't done — go back to §1.
- `## Signatures` — `@product` approves AC/Limitations/Proof, `@owner` confirms manual
  tests local+prod, `@eng` final. Real names when known, placeholder roles otherwise.
- `## Reversibility` — only when §2e produced one. (/scope-only.)

**Provenance rule** (single issue and epic children alike): an AC line or Limitations
item sourced from §0 carries its citation inline — `(per Ben, 8/14 call: "…")`. Limitations
items name who deferred it and when, so a later review finding that relitigates it gets an
evidence-backed dismissal instead of a judgment call. Uncited lines are fine; fake
citations are not.

**Epic** — a Linear **project** plus one child issue per story:

- Project description = the same template at project level: Requirement / Context /
  Acceptance Criteria / Limitations / Size & Order (phases, issue-linked, fib estimates
  summing to the stated time budget). Design decisions, hazards, and reversibility fold
  into Context and Limitations — no extra sections. Exemplar: off-git `c9bdadb3cdfc`
  (ENGH-335..343).
- Children carry the deep per-story detail (same section shape as a single issue), sized to
  one context window each.
- **Blocking relations ARE the dependency DAG** — `issueRelationCreate` per `needs` edge.
  `/epic` reads them to pick the next story, so they must be complete before any lane spawns.

## 5. Edit, then show the draft. Stop.

Draft fast, then make one cutting pass before rendering — this is where Write Simply
actually happens. Per sentence: can a plain word replace a fancy one? Can it be shorter
with nothing lost? Does it change what the lane builds? No → cut. Then check the other
direction: could a lane pick this up without asking a question? Missing fact → add it.

Render the full draft(s) — title, team, description(s), and for an epic the story list +
DAG. **Stop.** Wait for "go" or edits. Do not write yet.

## 6. On "go": write to Linear

Via the `linear` skill: `issueCreate` (single), or `projectCreate` + `issueCreate` per child
+ `issueRelationCreate` per DAG edge (epic). Set state Backlog, assignee the user, labels
per repo conventions. §0 fed the brief → also add the `evidence-grounded` label (create
once per team if missing) so review-rounds-per-PR can be compared against uncited briefs. Bodies via `--variables-file` — never echo markdown through the shell.
Verify `success: true` on every mutation and re-read the project/issue after save (Linear
silently drops some markdown — tables/checkboxes — on bad input). Return:

> `<TEAM-123>` created. Run `/pickup <TEAM-123> <base>` to start a lane.

For an epic:

> Project `<name>` + `<N>` children created. Run `/epic <project> <base>` to review
> story order and spawn the first child lane.

## 7. Commit the glossary edit — if §2c touched `CONTEXT.md`

`CONTEXT.md` is a **project-repo file** — left uncommitted in the cockpit it orphans (lanes
branch off `origin/main` and never see it) and stalls every `wt`/`/pickup` fast-forward.
In the **project repo**, if §2c changed `CONTEXT.md`:

```bash
git -C "$REPO" diff --quiet -- CONTEXT.md || \
  { git -C "$REPO" add CONTEXT.md; \
    git -C "$REPO" commit -q -m "docs: pin <terms> in CONTEXT.md glossary"; }
```

- Stage **`CONTEXT.md` only** — never `git add -A`/`.`; the cockpit may hold unrelated dirty work.
- This is the one project-repo write `/scope` makes (docs-only). Commit only; **never push**.
- No `CONTEXT.md` change this run → skip silently.

## Stop conditions

- After §1 clarifying questions — wait for answers.
- After §5 draft — wait for "go".
- After §6 write — done. The user runs `/pickup <id>` (or `/epic <project>`) next. The §7
  `CONTEXT.md` docs-commit is the only project-repo write; never edit code from this command.
