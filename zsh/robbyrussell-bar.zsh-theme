# robbyrussell-bar.zsh-theme
# robbyrussell theme + a status bar showing battery % and time

function _status_bar_precmd() {
  # Read battery percentage
  local bat_pct=""
  if [[ -r /sys/class/power_supply/BAT1/capacity ]]; then
    bat_pct=$(</sys/class/power_supply/BAT1/capacity)
  fi

  # Read AC status
  local ac_online=""
  if [[ -r /sys/class/power_supply/AC1/online ]]; then
    ac_online=$(</sys/class/power_supply/AC1/online)
  fi

  # Color-code battery level
  local bat_color
  if [[ -n "$bat_pct" ]]; then
    if (( bat_pct > 50 )); then
      bat_color="%F{green}"
    elif (( bat_pct > 20 )); then
      bat_color="%F{yellow}"
    else
      bat_color="%F{red}"
    fi
  fi

  # Build left side: battery info
  local left_text=""
  local left_visible_len=0
  if [[ -n "$bat_pct" ]]; then
    local charge_state=""
    if [[ "$ac_online" == "1" ]]; then
      charge_state=" (Plugged in)"
    else
      charge_state=" (Battery)"
    fi
    left_text="${bat_color}🔋 ${bat_pct}%%${charge_state}%f"
    # Visible length: "🔋 " (3) + digits + "%" + charge_state
    left_visible_len=$(( 3 + ${#bat_pct} + 1 + ${#charge_state} ))
  fi

  # Build right side: time
  local time_str
  time_str=$(date +%H:%M:%S)
  local right_text="%F{white}${time_str}%f"
  local right_visible_len=${#time_str}

  # Calculate fill width
  # Format: "── <left> ───...─── <right> ──"
  # Bookend dashes: 3 left ("── ") + 3 right (" ──")
  local padding_overhead=$(( 3 + 3 ))
  if [[ -n "$left_text" ]]; then
    padding_overhead=$(( padding_overhead + 1 )) # space after left
  fi
  if [[ -n "$right_text" ]]; then
    padding_overhead=$(( padding_overhead + 1 )) # space before right
  fi

  local content_len=$(( left_visible_len + right_visible_len + padding_overhead ))
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
  print -P "%F{240}── ${left_text} %F{240}${fill} ${right_text} %F{240}──%f"
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
