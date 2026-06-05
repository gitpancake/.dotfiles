# Pi config

Tracked Pi agent config, symlinked into `~/.pi/agent` by `_link-dotfiles.sh` / `rewire-symlinks.sh`.

Tracked here:

- `AGENTS.md` — global Pi operating instructions
- `settings.json` — provider/model/UI/resource settings
- `models.json` — custom provider/model registry; secret values must stay in `~/.pi/agent/.env.local`
- `keybindings.json` — TUI keybindings
- `extensions/` — local TypeScript/JavaScript Pi extensions
- `prompts/` — prompt templates
- `skills/` — local skills
- `themes/` — custom themes
- `bin/` — helper executables used by Pi workflows

Never track Pi runtime state or secrets:

- `~/.pi/agent/.env.local`
- `~/.pi/agent/auth.json`
- `~/.pi/agent/sessions/`
- `~/.pi/agent/npm/`
- `~/.pi/agent/git/`

After adding a new file or directory here, run:

```bash
./rewire-symlinks.sh
```

Open Pi sessions may need `/reload` for extensions, skills, prompts, and keybindings to refresh.

Current local extensions:

- `impacted-tests.ts` — focused-test discovery and push/PR guard.
- `observability-tools.ts` — Axiom, LangSmith, Sentry, and combined debug tools. LangSmith `listRuns` maps recognized coding projects to LangSmith projects (`cartage-agent` → `agent-production`, `agents`/`ai-employees` → `employees-production`). Axiom dataset defaults map `cartage-agent` → `REDACTED-DATASET-NAME` and `agents`/`ai-employees` → `cartage-ai-employees`. Extend with `LANGSMITH_PROJECT_MAP` or `AXIOM_DATASET_MAP` entries like `new-app=new-langsmith-project` / `new-app=new-axiom-dataset`.
- `safety-rails.ts` — large-read nudges, cross-worktree write guard, Linear create guard.
- `session-discipline.ts` — Pi-native `/tree`/`/handoff`/error-streak nudges and `/pi-usage` counters.
