[[ -f "$HOME/.cargo/env" ]] && . "$HOME/.cargo/env"

# Make nvm-managed node available in non-interactive shells without the lazy-load wrapper.
# Without this, sub-shells (tools, scripts, tmux panes) hit "command not found: _zsh_nvm_load"
# because .zshrc (where zsh-nvm sets up the lazy wrappers) is never sourced for non-interactive zsh.
export NVM_DIR="$HOME/.nvm"
if [[ -s "$NVM_DIR/alias/default" ]]; then
  export PATH="$NVM_DIR/versions/node/$(cat $NVM_DIR/alias/default)/bin:$PATH"
fi

# Machine-local secrets and env overrides. Lives outside the dotfiles repo so it's
# never tracked. Optional — absent on fresh machines until you populate it.
[[ -f "$HOME/.zshenv.local" ]] && source "$HOME/.zshenv.local"
