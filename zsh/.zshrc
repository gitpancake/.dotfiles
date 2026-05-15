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
alias cls="clear"
alias agent-watch="watch -tcn2 ~/.tmux/agent-board.sh"

# `g` is oh-my-zsh's `git` alias by default. Override with a function so
# `g checkout <branch>` cds to the worktree when that branch is already
# checked out elsewhere (instead of git's "already used by worktree" fatal).
# All other `g …` invocations fall through to plain `git`.
unalias g 2>/dev/null
g() {
  if [[ "$1" == "checkout" && $# -eq 2 && "$2" != -* ]]; then
    local branch="$2"
    local wt_path
    wt_path=$(git worktree list --porcelain 2>/dev/null | awk -v b="refs/heads/$branch" '
      /^worktree / { path=$2 }
      $0 == "branch " b { print path; exit }
    ')
    local here
    here=$(git rev-parse --show-toplevel 2>/dev/null)
    if [[ -n "$wt_path" && "$wt_path" != "$here" ]]; then
      echo "g: '$branch' lives at $wt_path — cd-ing there"
      cd "$wt_path"
      return
    fi
  fi
  command git "$@"
}

unalias art 2>/dev/null
# Start (or hand off) the commit-watcher daemon so reactive `art watch`
# panes pick up new merges to the current repo's main branch. The
# watcher is a global singleton, but the repo it watches is dynamic: it
# follows the repo containing $PWD. If a watcher is already running on
# a different repo, we kill it and start one on this repo.
#
# No-op if the watcher script or config is missing. Logs go to
# /tmp/commit-watcher.log.
_kill_and_wait() {
  local pid=$1
  kill "$pid" 2>/dev/null || return
  local i=0
  while (( i < 10 )) && ps -p "$pid" >/dev/null 2>&1; do
    sleep 0.1
    (( i++ ))
  done
}
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
      _kill_and_wait "$existing_pid"
    fi
  fi

  COMMIT_WATCHER_REPO="$repo" nohup python3 "$watcher" > /tmp/commit-watcher.log 2>&1 &
  disown
  echo "art: commit-watcher started (pid $!) repo=${repo:-config-default}"
}
# Start the audio-watcher daemon when `art watch` runs. Captures system
# output via the BackgroundMusic loopback device and emits onset/energy/
# tempo state for the renderer. Singleton enforced by flock inside the
# watcher; this guard just avoids spawning a second one when one is alive.
art_ensure_audio_watcher() {
  local watcher="$HOME/.dotfiles/scripts/audio-watcher.py"
  [[ -f "$watcher" ]] || return 0

  local lock="$HOME/.local/share/art/audio-watcher.lock"
  if [[ -f "$lock" ]]; then
    local existing_pid
    existing_pid=$(head -1 "$lock" | tr -d '[:space:]')
    if [[ -n "$existing_pid" ]] && \
       ps -p "$existing_pid" -o command= 2>/dev/null | grep -q audio-watcher.py; then
      _kill_and_wait "$existing_pid"
    fi
  fi

  nohup python3 "$watcher" > /tmp/audio-watcher.log 2>&1 &
  disown
  echo "art: audio-watcher started (pid $!)"
}
art() {
  local name="${1:-hologram}"
  [[ $# -gt 0 ]] && shift
  local script="$HOME/.local/share/art/${name}.py"
  if [[ ! -f "$script" ]]; then
    echo "Unknown art: $name"
    echo "Available: $(printf '%s\n' ~/.local/share/art/*.py 2>/dev/null | xargs -n1 basename -s .py | tr '\n' ' ')"
    return 1
  fi
  if [[ "$name" == "watch" ]]; then
    art_ensure_commit_watcher
    art_ensure_audio_watcher
  fi
  python3 "$script" "$@"
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

# env-edit: list/edit/delete keys in .env.local without opening vim.
# Usage:
#   env-edit              fzf-pick a key, then prompt for new value (hidden input)
#   env-edit KEY          target KEY directly (added if missing)
#   env-edit -l           list keys only (values never printed)
#   env-edit KEY --reload after edit, `set -a; source .env.local; set +a` into current shell
# Set ENV_EDIT_AUTO_RELOAD=1 to make --reload the default.
# At new-value prompt: empty=keep, "-"=delete.
env-edit() {
  local file=".env.local"
  [[ -f "$file" ]] || { echo "no $file in $PWD"; return 1 }

  if [[ "$1" == "-l" || "$1" == "--list" ]]; then
    grep -E '^[A-Z_][A-Z0-9_]*=' "$file" | cut -d= -f1
    return
  fi

  local key="$1"
  if [[ -z "$key" ]]; then
    if ! command -v fzf >/dev/null; then
      echo "fzf required for picker, or pass key as arg"
      return 1
    fi
    key=$(grep -E '^[A-Z_][A-Z0-9_]*=' "$file" | cut -d= -f1 | fzf --prompt="env key> ") || return 1
  fi

  local current
  current=$(awk -F= -v k="$key" '$1==k {sub(/^[^=]*=/, ""); print; exit}' "$file")
  if [[ -n "$current" ]]; then
    echo "current $key=${current:0:4}… (${#current} chars)"
  else
    echo "$key not present — will add"
  fi

  printf "new value (empty=keep, '-'=delete): "
  local new
  read -rs new
  echo

  case "$new" in
    "")
      echo "kept"
      return
      ;;
    "-")
      awk -v k="$key" 'BEGIN{FS=OFS="="} $1!=k' "$file" > "$file.tmp" && mv "$file.tmp" "$file"
      echo "deleted $key"
      ;;
    *)
      if grep -qE "^${key}=" "$file"; then
        awk -v k="$key" -v v="$new" 'BEGIN{FS=OFS="="} $1==k {print k"="v; next} {print}' "$file" > "$file.tmp" && mv "$file.tmp" "$file"
        echo "updated $key"
      else
        printf '%s=%s\n' "$key" "$new" >> "$file"
        echo "added $key"
      fi
      ;;
  esac

  if [[ "$2" == "--reload" || "$ENV_EDIT_AUTO_RELOAD" == "1" ]]; then
    set -a
    source "$file"
    set +a
    echo "reloaded into shell"
  fi
}

# gcloud
[[ -f "/opt/homebrew/share/google-cloud-sdk/path.zsh.inc" ]] && source "/opt/homebrew/share/google-cloud-sdk/path.zsh.inc"
[[ -f "/opt/homebrew/share/google-cloud-sdk/completion.zsh.inc" ]] && source "/opt/homebrew/share/google-cloud-sdk/completion.zsh.inc"
