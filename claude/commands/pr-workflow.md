# PR / Branch Workflow Skill

Enforces feature branch strategy. Main is sacred — all work happens on branches.

## When This Activates
When creating branches, making commits, preparing PRs, or merging work.

## Branch Strategy

### Main is Protected
- Main should always be deployable. Never commit directly to main.
- All work happens on feature branches branched from main.
- Merge to main only via PR (or explicit merge after review).

### Branch Naming
- `feature/short-description` — new functionality
- `fix/short-description` — bug fixes
- `refactor/short-description` — restructuring without behavior change
- Keep names lowercase, hyphenated, under 40 chars.

### Branch Lifecycle
1. `git checkout main && git pull` — start from latest main.
2. `git checkout -b feature/description` — create feature branch.
3. Work, commit in logical chunks as you go.
4. When complete: push and create PR.
5. After merge: delete the feature branch locally and remotely.

## Commit Discipline
- Commit after each isolated chunk of work (feature, bugfix, refactor).
- Commit messages: concise, focused on the "why" not the "what."
- Don't bundle unrelated changes in one commit.
- Schema changes, backend logic, and frontend work should be separate commits even in the same PR.

## Pull Requests
- PR title: short, under 70 chars, describes the change.
- PR body: Summary (what and why), Test plan (how to verify).
- One PR per feature/fix. Don't let PRs grow massive — split if > 500 lines changed.
- Review the full diff before creating the PR. No debug code, no TODOs.

## Merging
- Prefer squash merge for clean history on main.
- Delete feature branch after merge.
- Pull main after merge to stay current: `git checkout main && git pull`.

## When Projects Are Small
- Early-stage projects (solo, < 1 week old) can commit to main directly.
- Once a project has structure and stability, switch to feature branches.
- The transition point: when a bad commit to main would cost you more than 10 minutes to fix.

## Principle
Main reflects reality. Branches are experiments. PRs are the gate between them.
