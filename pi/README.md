# Pi config

Tracked Pi agent config, symlinked into `~/.pi/agent` by `_link-dotfiles.sh` / `rewire-symlinks.sh`.

Tracked here:

- `AGENTS.md` — global Pi operating instructions
- `settings.json` — provider/model/UI/resource settings
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
- `~/.pi/paperclips/`

After adding a new file or directory here, run:

```bash
./rewire-symlinks.sh
```

Open Pi sessions may need `/reload` for extensions, skills, prompts, and keybindings to refresh.
