#!/bin/bash
# Syncs new plan files written to ~/.claude/plans/ into the Obsidian vault
# with human-readable filenames derived from the H1 title.

FILE_PATH=$(jq -r '.tool_input.file_path // empty' 2>/dev/null)

# Only handle files inside ~/.claude/plans/
[[ "$FILE_PATH" == "$HOME/.claude/plans/"* ]] || exit 0

OBSIDIAN_BASE="${CLAUDE_OBSIDIAN_PLANS_DIR:-$HOME/Documents/obsidian-vault/Henry Vault/04-PROJECTS/Claude Plans}"
FNAME=$(basename "$FILE_PATH")

# Read H1 title; fall back to filename stem
TITLE=$(grep -m1 "^# " "$FILE_PATH" 2>/dev/null | sed 's/^# //')
[[ -z "$TITLE" ]] && TITLE="${FNAME%.md}"

# Make filename-safe: normalise dashes, strip unsafe chars, collapse spaces
SAFE=$(echo "$TITLE" \
  | sed 's/ — / - /g; s/—/-/g; s/: / - /g; s|/|-|g' \
  | tr -d '`*?<>|"\\' \
  | sed 's/  */ /g; s/^ //; s/ $//')

# Agent sub-plans (slug contains -agent-<hex>) go to Agent Outputs/
if echo "$FNAME" | grep -qE '\-agent\-[a-f0-9]{10,}'; then
  DEST_DIR="$OBSIDIAN_BASE/Agent Outputs"
else
  DEST_DIR="$OBSIDIAN_BASE"
fi

DEST="$DEST_DIR/$SAFE.md"
[[ -f "$DEST" ]] && DEST="$DEST_DIR/$SAFE (2).md"

cp "$FILE_PATH" "$DEST" 2>/dev/null
