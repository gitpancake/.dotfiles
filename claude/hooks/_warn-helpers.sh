#!/usr/bin/env bash
# Shared helpers for warning hooks.

# Fire a named warning at most once per session/group.
# Usage: shouldFireOnce <tag> <warned_file>
# Returns 0 (should fire) or 1 (already fired).
shouldFireOnce() {
  local tag=$1 file=$2
  grep -qx "$tag" "$file" && return 1
  echo "$tag" >> "$file"
  return 0
}
