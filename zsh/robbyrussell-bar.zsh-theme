# robbyrussell-bar.zsh-theme
# robbyrussell theme + a status bar showing time

function _status_bar_precmd() {
  # Build right side: time
  local time_str
  time_str=$(date +%H:%M:%S)
  local right_text="%F{white}${time_str}%f"
  local right_visible_len=${#time_str}

  # Calculate fill width
  # Format: "── ───...─── <right> ──"
  # Bookend dashes: 3 left ("── ") + 3 right (" ──") + 1 space before right
  local content_len=$(( right_visible_len + 7 ))
  local fill_len=$(( COLUMNS - content_len ))
  if (( fill_len < 1 )); then
    fill_len=1
  fi

  # Build the fill string
  local fill=""
  local i
  for (( i = 0; i < fill_len; i++ )); do
    fill+="─"
  done

  # Print the status bar
  print -P "%F{240}── ${fill} ${right_text} %F{240}──%f"
}

# Register precmd hook (safe for multiple sources)
autoload -Uz add-zsh-hook
add-zsh-hook precmd _status_bar_precmd

# Original robbyrussell prompt (unchanged)
PROMPT="%(?:%{$fg_bold[green]%}%1{➜%} :%{$fg_bold[red]%}%1{➜%} ) %{$fg[cyan]%}%c%{$reset_color%}"
PROMPT+=' $(git_prompt_info)'

ZSH_THEME_GIT_PROMPT_PREFIX="%{$fg_bold[blue]%}git:(%{$fg[red]%}"
ZSH_THEME_GIT_PROMPT_SUFFIX="%{$reset_color%} "
ZSH_THEME_GIT_PROMPT_DIRTY="%{$fg[blue]%}) %{$fg[yellow]%}%1{✗%}"
ZSH_THEME_GIT_PROMPT_CLEAN="%{$fg[blue]%})"
