# zsh

Zsh configuration. Symlinked into `~` by `install.sh` / `install-mac.sh`.

## Files

| File | Purpose |
| --- | --- |
| `.zshenv` | Loaded by **every** zsh invocation (interactive, non-interactive, scripts). Use for `PATH` exports that subprocesses need. |
| `.zshrc` | Loaded for interactive shells. Oh My Zsh, nvm, brew, aliases, theme. |
| `robbyrussell-bar.zsh-theme` | Custom Oh My Zsh theme — `robbyrussell` + a right-aligned time status printed via `precmd` hook (not `PROMPT`, to avoid cursor glitches). |

## Install

The installers symlink:

```
~/.zshenv → dotfiles/zsh/.zshenv
~/.zshrc  → dotfiles/zsh/.zshrc
```

The custom theme is copied into `$ZSH_CUSTOM/themes/` by the installer.

## Editing

After changes, lint with `zsh -n <file>` before sourcing.
