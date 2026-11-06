#!/usr/bin/env bash
# The one PreToolUse guard hook. Parses the tool call once, then runs each
# enabled guard in guards.json in order; the first decision ends the chain.
# Guards that only ask sit last, so a deny from any guard still wins over an
# ask, as it did when each guard was its own hook.
#
# Turn a guard off for one shell: CLAUDE_GUARDS_DISABLED="tail-pipe,prod-db".
# Turn it off for good: "isEnabled": false in guards.json.

set -u

hooksDir=$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")
source "$hooksDir/_guard.sh"
guard_read_input

disabledGuards=",${CLAUDE_GUARDS_DISABLED:-},"

while IFS=$'\t' read -r guardName guardFile guardCheck guardScope; do
  [[ "$disabledGuards" == *",$guardName,"* ]] && continue
  case "$guardScope" in
    lane) $GUARD_IS_LANE || continue ;;
    cockpit) $GUARD_IS_LANE && continue ;;
  esac
  source "$hooksDir/$guardFile"
  "$guardCheck"
done < <(jq -r '.guards[] | select(.isEnabled) | [.name, .file, .check, .scope] | @tsv' "$hooksDir/guards.json")

exit 0
