# Path to your Oh My Zsh installation.
export ZSH="$HOME/.oh-my-zsh"

# Set name of the theme to load
ZSH_THEME="robbyrussell-bar"

# Which plugins would you like to load?
plugins=(git)

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

# Homebrew configuration (load first)
if [[ -x /home/linuxbrew/.linuxbrew/bin/brew ]]; then
  eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv zsh)"
elif [[ -x /opt/homebrew/bin/brew ]]; then
  eval "$(/opt/homebrew/bin/brew shellenv zsh)"
elif [[ -x /usr/local/bin/brew ]]; then
  eval "$(/usr/local/bin/brew shellenv zsh)"
fi

# NVM configuration (prioritizes NVM Node over Homebrew Node)
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"

# Auto-use NVM's default Node version
if command -v nvm >/dev/null 2>&1; then
  nvm use default >/dev/null 2>&1
fi

# PATH configuration (add local bin)
export PATH="$HOME/.local/bin:$PATH"