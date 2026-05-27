[[ -f "$HOME/.cargo/env" ]] && . "$HOME/.cargo/env"

# Make nvm-managed node available in non-interactive shells without the lazy-load wrapper.
# Without this, sub-shells (tools, scripts, tmux panes) hit "command not found: _zsh_nvm_load"
# because .zshrc (where zsh-nvm sets up the lazy wrappers) is never sourced for non-interactive zsh.
export NVM_DIR="$HOME/.nvm"
if [[ -s "$NVM_DIR/alias/default" ]]; then
  nvm_ver=$(cat "$NVM_DIR/alias/default" 2>/dev/null)
  [[ -d "$NVM_DIR/versions/node/$nvm_ver/bin" ]] && export PATH="$NVM_DIR/versions/node/$nvm_ver/bin:$PATH"
  unset nvm_ver
fi

# tix preload hook — run the dotfiles' status reconciler before each tix launch.
# tix itself is a pure reader (see github.com/gitpancake/tix); status: derivation
# from live worktrees + merged PRs lives here in claude/scripts/ticket-status-sync.py.
export TIX_PRELOAD_HOOK="$HOME/.claude/scripts/ticket-status-sync.py"

# wt-lanes (github.com/gitpancake/wt-lanes): tell `wt` to flip a ticket's
# status: → active on spawn by invoking the same reconciler with the slug.
export WT_TICKET_SYNC="$HOME/.claude/scripts/ticket-status-sync.py"

# Skip the auto-attached lane-watch monitor pane on `wt` spawn. Preference:
# single pane per lane, no split. Re-enable per-spawn by unsetting or =0.
export WT_NO_WATCH=1

# Default lane model: sonnet. Cockpit/planning stay opus via global settings.json.
# Cache_read on lanes (long heads-down coding, 200-500 turns) dominates cost;
# sonnet cache_read is 5x cheaper ($0.30/M vs $1.50/M). Override per-lane with
# `WT_MODEL=opus wt ...` when a lane genuinely needs Opus-grade reasoning.
export WT_MODEL=sonnet

# Lane Claude launcher: slim MCP set (HTTP-only), ulimit -t 1800 on the
# process tree, and PATH-shimmed bun w/ a 5min wall-clock timeout. Caps the
# memory leak from orphan `tsc --noEmit` (4GB+) when a lane Claude dies
# mid-typecheck. See claude/bin/claude-lane + claude/lane-bin/bun +
# claude/hooks/lane-reaper.sh.
export WT_CLAUDE="$HOME/.local/bin/claude-lane"

# Machine-local secrets and env overrides. Lives outside the dotfiles repo so it's
# never tracked. Optional — absent on fresh machines until you populate it.
[[ -f "$HOME/.zshenv.local" ]] && source "$HOME/.zshenv.local"
