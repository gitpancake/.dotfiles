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
docs-PR in §7 (a throwaway-worktree branch, never a commit on the cockpit checkout). Lanes get the brief via `linear-brief.sh` materialization at `/pickup`
time, not from anything /scope leaves on disk.

If `$ARGUMENTS` is empty, infer the problem from conversation context — what was just
discussed, debugged, or decided. Summarize your interpretation in 1–2 sentences and proceed.
No relevant context either → ask for a problem statement and stop.

**The user writes the Requirement and the Limitations** (global CLAUDE.md §Pace). Those two
sections carry the judgment — what we are building and what we are not — and a brief whose
judgment was drafted by the model gets a reflexive "go". /scope never drafts either one.
It grills them (§1), fills in every other section, and puts the user's words into the
brief with typos fixed and nothing else changed.

## 0. Evidence pass — before the grill

The brief's slots (Requirement / Context / Limitations / AC / Proof) get filled from
evidence, not the user's recollection.

**Discovery is automatic, not user-prompted.** Always run one semantic search of the
transcript corpus on the distilled problem statement — this catches the meeting the user
forgot discussed it:

```bash
~/.dotfiles/scripts/pocket.py search "<problem statement key terms>" --limit 8
```

Results carry `recordingId`/`recordingTitle`/`relevanceScore` + speaker-labelled excerpts.
A relevant hit → pull that recording's detail. Then pull anything the user named or the
request traces to:

- **Granola** (`granola` skill): the meeting's note + action items. For who-said-what, use
  `granola.py transcript <id> --text` — the note detail's `transcript` field is null in
  practice; the transcript endpoint attributes each line (`me`/`them`, real names once
  speaker tags are set up).
- **Pocket** (`pocket` skill): the verbatim transcript — the throwaway constraints
  ("oh, and it has to…") live here, not in the summary. Also sweep
  `pocket.py actions` across the topic's window: items shaped "not doing / later / v2"
  are pre-cited Limitations candidates.
- **Slack** (`cartage-bots` skill): the originating thread. Support-originated → add the
  Plain thread (`plain-api` skill).

Distill an evidence pack:

- Candidate requirements — verbatim quote + speaker. Speaker attribution: named where the
  source names them; an anonymous diarized turn (`SPEAKER_NN`, Granola `them`) may be
  name-inferred from attendees/self-intros but the citation must say `(speaker inferred)`.
- Constraints + success criteria mentioned.
- **Explicitly-deferred items** — who deferred, when (the `actions` sweep feeds this).
- Contradictions: source vs source, or source vs `$ARGUMENTS`.

Search misses and no traceable source → skip silently; §1 grills from scratch as before.
Never fabricate a citation — an uncited AC line is honest, a fake quote is not.

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

**Then collect the two sections the user owns.** Ask for them once the grill is done, in
one message, and stop:

> Write the **Requirement** (the outcome, 2–3 sentences) and the **Limitations** (what is
> out of scope, each with its why). Your words — I will not draft them.

Offer raw material, never a draft: the §0 quotes that bear on the outcome, and the
deferred items as a plain list of candidates the user may adopt, reword, or drop. A
Requirement already written out in `$ARGUMENTS` in the user's own sentences counts —
quote it back and ask only for the Limitations. If what comes back is vague ("works
correctly", a Limitation with no why), say which sentence and why, and ask again; do not
repair it yourself.

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

### 2e. Design pass (POSD §11 + GoF) — only for structural choices

A structural decision — new data model, routing-key shape, service boundary, vendor
adapter, error-propagation strategy, a second variant of something that exists once — is
designed here, not in the lane. The lane builds a shape; it does not choose one. The
reference is `~/.claude/docs/design-principles.md` (§Design Patterns for the catalog).

1. **Design it twice.** Sketch ≥2 alternatives before writing the brief. Two bullets each:
   shape, cost, what it makes easy/hard. Pick one and say why. **Even when the answer
   feels obvious, force a second sketch.** First idea is rarely best for hard problems.
2. **Name the pattern, or name "none".** For each alternative, the catalog pattern it is
   (`GoF:Strategy`, `GoF:Adapter`, …) and the **force** that earns it: an axis that varies
   at ≥2 sites (Strategy / State), a construction with ordering rules (Builder), an
   interface we don't own (Adapter), a behavior layered on an unchanged core (Decorator),
   one emitter with listeners it must not know (Observer), a subsystem behind one call
   (Facade — usually the workflow that already exists). No force → no pattern → a plain
   function wins. A pattern the reader has to look up loses to code they can read. Most
   GoF shapes collapse in TypeScript to a function type, a discriminated union, or a
   `Record<Kind, …>` — the brief names that concrete shape, not the diagram.
3. **Maintainability gate** on the chosen shape. One line per item; the answers are the
   `## Design` section. An item you can't answer is a hole in the design, not in the brief.
   - **Reads without comments** (POSD §13 / §18). Every new module, fn, and type is named
     so its intent is the name. A spot where you'd want a comment is a rename or an
     extract, and the brief names it now. A comment is a failure of this gate, not a fix.
   - **Layer.** Read the `## Architecture` section of the repo's root `CLAUDE.md` now and
     quote the line that places this work — never recite a layering from memory. Which
     layer owns the logic, and what each hands the next. In cartage-agent new business
     logic lives in a use case behind its ports; a legacy workflow is where code moves
     from, not where new code goes.
   - **Deep, not shallow** (POSD §4 / §5). The new surface's public interface in ≤3 lines,
     and the decision it hides so callers stop repeating it. A wide interface over a thin
     body is the wrong cut.
   - **One canonical home** (PP §11). The knowledge this introduces — a mapping, a rule, a
     format — lives in exactly one named place. Two places is a future drift bug.
   - **Extension point.** Where the next variant goes without editing the existing ones.
     No answer → the abstraction is wrong or premature; say which and pick the plain shape.
   - **Test seam** (PP §48). The unit the automated test drives through its public surface,
     and what it stubs at the edge. Needs a mock of an internal → the boundary is wrong.
   - **Smell sweep.** Adjacent code already showing the smell this shape fixes — the same
     `switch` on kind elsewhere, telescoping params, shotgun surgery across the mirror. In
     scope → cite the refactoring by its catalog name. Out of scope → Limitations, with why.

For reversibility (PP §14): if the chosen approach is hard to back out of (DB column we'd
have to migrate off, vendor we'd have to swap, public type shape), add a `## Reversibility`
section. State: what locks us in, what would force a change, rough escape cost. If the choice
deserves an ADR (hard to reverse + surprising + a real trade-off), say so — `/grill-with-docs`
will offer to write it.

Routine choices (which existing helper to call, which existing table to extend) — one line
in `## Surface area`: `Shape: extends <helper>; no new abstraction.` Skip the rest of §2e.
Reserve the pass for decisions that survive past the PR.

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

**Single issue** — the house template (global CLAUDE.md §Ticket Lifecycle) plus the three
/scope-only sections, in order:

- `## Requirement` — the user-facing outcome, 2–3 sentences. **The user's text from §1**,
  typos fixed, nothing else changed.
- `## Context` — why: the refined problem, mirror reference, decisions from the grill,
  gotchas quoted from project CLAUDE.md.
- `## Surface area` — mirror / ≤8 starting files with one-line reasons / prerequisites +
  unconfirmed mechanisms from §2d. Routine shape → the one `Shape:` line. (/scope-only.)
- `## Design` — only when §2e ran. The chosen shape as concrete TypeScript (the fn type,
  the union, the `Record<Kind, …>`), its pattern name and the force that earns it, the
  rejected alternative and what was worse about it, and the seven gate answers. Name the
  modules and fns the lane will create, so the names are decided before the code. The
  lane builds this shape; `/code-review` holds the diff to it. (/scope-only.)
- `## Acceptance Criteria` — checkboxes, each a testable yes/no. Never "works correctly".
- `## Limitations` — out of scope, each item with its why (the why kills scope creep and
  relitigating). **The user's text from §1.** A limit that exploration turns up later
  (§2) is put to the user as a question; it enters the brief only in the words they give.
- `## Proof` — defined now, before work starts. **Manual Tests**: concrete steps + the
  evidence each produces. A step that needs the running app runs on the hosted dev env
  (`/host-dev`, per-branch VM at a stable URL) — write "on the dev env", never "local":
  a lane reads "local" as an order to boot a dev server on the cockpit machine. The lane
  produces the screenshots itself (repo `docs/testing/playwright.md`), so name the screen
  and the state each one must show.
  **Automated Tests**: the tests the lane will add. If you can't name what would prove
  it works, the AC aren't done — go back to §1.
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
- The user writes the project's Requirement and Limitations. A child's Requirement and
  Limitations quote the part of the project's that the story delivers; no new judgment
  enters at child level, and a limit that only one story needs goes to the user as a
  question.
- Children carry the deep per-story detail (same section shape as a single issue), sized to
  one context window each. A structural story carries its own `## Design`; a shape shared
  by several stories is decided once in the project Context and each child cites it, so no
  lane re-decides it.
- **Sweep rule**: a brief whose work is "do X across N orgs / N files / N skills" with N > ~5
  is NOT a single ticket — it's an epic with children batched to one context window each
  (proof: ENGH-863 burned 15 lane sessions, ENGH-866 burned 8, both fleet-wide sweeps that
  exhausted context and respawned on a handoff chain). Slice by org/file batch at scope
  time; never rely on the lane's respawn cap to absorb an oversized brief.
- **Blocking relations ARE the dependency DAG** — `issueRelationCreate` per `needs` edge.
  `/epic` reads them to pick the next story, so they must be complete before any lane spawns.

## 5. Edit, then show the draft. Stop.

Draft fast, then make one cutting pass before rendering — this is where Write Simply
actually happens. Per sentence: can a plain word replace a fancy one? Can it be shorter
with nothing lost? Does it change what the lane builds? No → cut. Then check the other
direction: could a lane pick this up without asking a question? Missing fact → add it.
Then `## Design`: every pattern named points at its force and a site count; a pattern
named because it is familiar gets cut and the shape becomes a function. Every new name
in it is one a reader understands without a comment.

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

## 7. Ship the glossary edit — if §2c touched `CONTEXT.md`

`CONTEXT.md` is a **project-repo file**, and cartage repos gate `main` behind required
status checks — a commit on the cockpit's local `main` can never be pushed, so it strands
as unpushable noise that lanes (branched off `origin/main`) never see and that wedges every
`wt`/`/pickup` fast-forward. **Never commit to the cockpit's checkout.** Land the pin on
origin via a docs-only PR from a throwaway worktree:

```bash
[ -n "$(git -C "$REPO" diff --name-only -- CONTEXT.md)" ] && {
  git -C "$REPO" fetch -q origin main
  BR="docs/pin-<first-term-slug>"   # slug from the pinned term, no ids
  TMP=$(mktemp -d)
  git -C "$REPO" worktree add -q "$TMP" -b "$BR" origin/main
  cp "$REPO/CONTEXT.md" "$TMP/CONTEXT.md"
  git -C "$TMP" add CONTEXT.md
  git -C "$TMP" commit -q -m "docs: pin <terms> in CONTEXT.md glossary"
  git -C "$TMP" push -qu origin "$BR"
  gh pr create -R <owner/repo> --head "$BR" \
    --title "docs: pin <terms> in CONTEXT.md glossary" \
    --body "Glossary-only: pins <terms> from a /scope grill. No code changes."
  gh pr merge -R <owner/repo> "$BR" --auto --squash
  git -C "$REPO" worktree remove -f "$TMP" && git -C "$REPO" branch -D "$BR"
  git -C "$REPO" checkout -- CONTEXT.md
}
```

- Copy the **whole file** — `CONTEXT.md` is glossary-only by contract, so every uncommitted
  line in it is a pin that belongs in the PR. Never stage anything else.
- The final `checkout -- CONTEXT.md` restores the cockpit tree clean (a dirty tracked file
  blocks the next fast-forward); the pin returns on the next `git pull` after the PR merges.
- Auto-merge is enabled on both cartage repos and repo checks are docs-tolerant; if
  `--auto` errors, report the PR link and leave it — never bypass checks, never commit to
  `main` as a fallback.
- This docs-only PR is exempt from `/ship`'s Linear-ticket rule — a glossary pin needs no
  team-reference ticket.
- No `CONTEXT.md` change this run → skip silently.

## Stop conditions

- After §1 clarifying questions — wait for answers.
- After the §1 ask for the Requirement and the Limitations — wait for the user's text.
  Never proceed on a version you wrote.
- After §5 draft — wait for "go".
- After §6 write — done. The user runs `/pickup <id>` (or `/epic <project>`) next. The §7
  `CONTEXT.md` docs-PR is the only project-repo write; never edit code from this command.
