# Path to your Oh My Zsh installation.
export ZSH="$HOME/.oh-my-zsh"

# Set name of the theme to load
ZSH_THEME="robbyrussell-bar"

# NVM lazy loading (must be set before oh-my-zsh loads zsh-nvm)
export NVM_LAZY_LOAD=true
export NVM_COMPLETION=true

# Which plugins would you like to load?
plugins=(git zsh-nvm zsh-autosuggestions zsh-syntax-highlighting)

source $ZSH/oh-my-zsh.sh

# Tab accepts autosuggestion if one exists, otherwise normal completion
_autosuggest_or_complete() {
  if [[ -n "$POSTDISPLAY" ]]; then
    zle autosuggest-accept
  else
    zle expand-or-complete
  fi
}
zle -N _autosuggest_or_complete
bindkey '\t' _autosuggest_or_complete

# Security: only allow known-safe node binaries to have nvm lazy-load wrappers.
# Without this, ANY `npm install -g` package gets a shell function that shadows
# system commands — a malicious package named "curl" or "git" would hijack them.
_nvm_allowed=(node npm npx corepack nvm pnpm pnpx yarn yarnpkg tsc tsserver vercel vc)
for cmd in $(_zsh_nvm_global_binaries 2>/dev/null); do
  (( ${_nvm_allowed[(Ie)$cmd]} )) || unset -f $cmd 2>/dev/null
done
unset _nvm_allowed

# Tmux pane title configuration
_update_tmux_pane_title() {
  if [[ -n "$TMUX" ]]; then
    local manual=$(tmux show-option -pqv @pane_manual)
    if [[ -n "$manual" ]]; then
      tmux set-option -p @pane_label "$manual"
    else
      local branch=$(git branch --show-current 2>/dev/null)
      local dir=$(basename "$PWD")
      if [[ -n "$branch" ]]; then
        tmux set-option -p @pane_label "$dir [$branch]"
      else
        tmux set-option -p @pane_label "$dir"
      fi
    fi
  fi
}

add-zsh-hook precmd _update_tmux_pane_title

# Aliases
alias config="vim ~/.zshrc"
alias reload="source ~/.zshrc"
alias ll="ls -la"
alias cdsp="claude --dangerously-skip-permissions"
unalias art 2>/dev/null
# Start (or hand off) the commit-watcher daemon so reactive `art watch`
# panes pick up new merges to the current repo's main branch. The
# watcher is a global singleton, but the repo it watches is dynamic: it
# follows the repo containing $PWD. If a watcher is already running on
# a different repo, we kill it and start one on this repo.
#
# No-op if the watcher script or config is missing. Logs go to
# /tmp/commit-watcher.log.
art_ensure_commit_watcher() {
  local watcher="$HOME/.dotfiles/scripts/commit-watcher.py"
  local config="$HOME/.dotfiles/scripts/commit-watcher.config.local"
  [[ -f "$watcher" && -f "$config" ]] || return 0

  local lock="$HOME/.local/share/art/commit-watcher.lock"
  local repo
  repo=$(git rev-parse --show-toplevel 2>/dev/null)

  if [[ -f "$lock" ]]; then
    local existing_pid existing_repo
    IFS=$'\t' read -r existing_pid existing_repo < "$lock"
    if [[ -n "$existing_pid" ]] && \
       ps -p "$existing_pid" -o command= 2>/dev/null | grep -q commit-watcher.py; then
      if [[ -z "$repo" || "$existing_repo" == "$repo" ]]; then
        return 0
      fi
      kill "$existing_pid" 2>/dev/null
      # Wait briefly for flock release; cap to ~1s.
      local i=0
      while (( i < 10 )) && ps -p "$existing_pid" >/dev/null 2>&1; do
        sleep 0.1
        (( i++ ))
      done
      echo "art: commit-watcher repo handoff: $existing_repo → ${repo:-config-default}"
    fi
  fi

  COMMIT_WATCHER_REPO="$repo" nohup python3 "$watcher" > /tmp/commit-watcher.log 2>&1 &
  disown
  echo "art: commit-watcher started (pid $!) repo=${repo:-config-default}"
}
art() {
  local name="${1:-hologram}"
  local script="$HOME/.local/share/art/${name}.py"
  if [[ ! -f "$script" ]]; then
    echo "Unknown art: $name"
    echo "Available: $(ls ~/.local/share/art/*.py 2>/dev/null | xargs -n1 basename | sed 's/\.py$//' | tr '\n' ' ')"
    return 1
  fi
  [[ "$name" == "watch" ]] && art_ensure_commit_watcher
  python3 "$script"
}

# Homebrew configuration (load first)
if [[ -x /home/linuxbrew/.linuxbrew/bin/brew ]]; then
  eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv zsh)"
elif [[ -x /opt/homebrew/bin/brew ]]; then
  eval "$(/opt/homebrew/bin/brew shellenv zsh)"
elif [[ -x /usr/local/bin/brew ]]; then
  eval "$(/usr/local/bin/brew shellenv zsh)"
fi

# NVM directory (lazy-loaded by zsh-nvm plugin)
export NVM_DIR="$HOME/.nvm"

# PATH configuration (add local bin)
export PATH="$HOME/.local/bin:$PATH"

# Zoxide (smart cd)
eval "$(zoxide init zsh)"

# fzf (fuzzy finder: Ctrl+R for history, Ctrl+T for files)
source <(fzf --zsh)
# bun completions
[ -s "$HOME/.bun/_bun" ] && source "$HOME/.bun/_bun"

# bun
export BUN_INSTALL="$HOME/.bun"
export PATH="$BUN_INSTALL/bin:$PATH"

# Prefix any command with a space to keep it out of history
setopt HIST_IGNORE_SPACE

export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"  # This loads nvm
[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"  # This loads nvm bash_completion

# gcloud
source "/opt/homebrew/share/google-cloud-sdk/path.zsh.inc"
source "/opt/homebrew/share/google-cloud-sdk/completion.zsh.inc"
