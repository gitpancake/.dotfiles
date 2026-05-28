---
description: Resume from handoff doc — most recent or matched by description.
argument-hint: "[--slim|--full] [description of which handoff — omit for the most recent]"
---

# /resume $ARGUMENTS

Pick up where a previous session left off. `/handoff` writes durable docs to
`~/.claude/handoffs/`; this command finds the right one, reads it, and continues the work.

**Resume loads context into THIS session and continues inline. It NEVER spawns a
worktree or lane.** Do not run `wt`, `/pickup`, `/epic`, or `git worktree add` from a
resume — the handoff is a thread to continue, not a ticket to pick up fresh. If the work
originated in a lane, the lane's worktree already exists; resume runs *inside* it. The
global "lane work → slash command" rule does NOT apply here — that rule is for *starting*
work, and resume is *continuing* it. Spawning a lane on resume is what produced 3
worktrees racing the same task; the whole point of resume is to avoid that.

**Budget discipline.** Resume rehydrates the session that needed a handoff — easy to burn
50K+ tokens chasing refs before any real work. Default to the leanest path that still
orients you; only chase refs when the handoff is thin or the next step is genuinely
ambiguous.

## 0. Parse flags

Strip leading flag from `$ARGUMENTS`:

- `--slim` → force slim mode (skip §3 ref-chase, do §3-lite only).
- `--full` → force full mode (always §3).
- neither → **auto** by handoff size: `wc -l <handoff>` ≥ 80 → slim; < 80 → full.

Remainder of `$ARGUMENTS` (if any) = description match for §1.

## 1. Find the handoff

```bash
ls -t ~/.claude/handoffs/*.md 2>/dev/null
```

- **No files** → tell the user there are no handoffs and stop.
- **description empty** → take the most recent (first line of `ls -t`).
- **description non-empty** → treat it as a description. Match against filename slugs
  (case-insensitive substring).
  - Exactly one match → use it.
  - Several matches → list them with dates, ask which, stop.
  - No match → use the most recent and say so explicitly ("no match for `<desc>` —
    resuming the latest instead").

## 2. Read it

Read the chosen file in full. It references other artifacts (briefs, PRDs, commits, PRs)
by path/URL rather than restating them.

- **slim mode**: do NOT pre-fetch refs. Pull a ref only when the next concrete action
  needs the value — never "to orient." A 12K handoff already names branch, next step,
  and anchors; chasing the brief + PR diff + 3 commits before doing anything is the
  failure mode this flag exists to prevent.
- **full mode**: follow references as needed before acting.

## 3. Re-orient

**slim** (§3-lite): one `git status` + branch check in cwd. Trust the handoff's
"done" / "next" claims unless they contradict `git status`. Skip brief re-read, skip
commit verification, skip PR fetch.

**full**: verify the world still matches the handoff — it was a snapshot:
- `git status` + branch in any repos the handoff names.
- The brief / ticket / plan it points at still exists and still says what the handoff claims.
- Anything the handoff lists as "done" is actually landed (commit present, PR merged).

Either mode — stale handoff (work moved on, named artifact gone) → surface the gap,
don't blindly execute.

## 4. Continue

Carry on with the work the handoff describes, **in this session**. The handoff's
"Suggested skills" are advisory hints about *how* to do the work (e.g. `tdd`, `diagnose`),
not a directive to spawn a lane — ignore any that would start a fresh worktree
(`pickup`/`epic`/`wt`). Give a two-line orientation ("Resumed from `<file>` (`<mode>`).
Picking up: `<next step>`.") and proceed — no need to re-summarise the whole handoff back
to the user.

## Stop conditions

- No handoffs, or an ambiguous multi-match description — ask or report, stop.
- Handoff is stale / its anchor artifact is missing — surface, stop for direction.
- Never: `wt`, `/pickup`, `/epic`, `git worktree add`. Resume continues inline only.
