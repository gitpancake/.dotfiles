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
art() {
  local name="${1:-hologram}"
  local script="$HOME/.local/share/art/${name}.py"
  if [[ -f "$script" ]]; then
    python3 "$script"
  else
    echo "Unknown art: $name"
    echo "Available: $(ls ~/.local/share/art/*.py 2>/dev/null | xargs -n1 basename | sed 's/\.py$//' | tr '\n' ' ')"
  fi
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
[ -s "/Users/henrypye/.bun/_bun" ] && source "/Users/henrypye/.bun/_bun"

# bun
export BUN_INSTALL="$HOME/.bun"
export PATH="$BUN_INSTALL/bin:$PATH"
