#!/bin/bash
# PreToolUse hook: restricts Read/Grep/Glob to /workspace/repos/.
# exit 0 = allow, exit 2 = block.

set -euo pipefail

input=$(cat)
tool=$(echo "$input" | jq -r '.tool_name // empty')

# Validates a file or directory path.
# Relative paths are anchored to /workspace (container cwd).
check_path() {
  local p="$1"
  [ -z "$p" ] && return 0

  case "$p" in
    /*) ;;
    *) p="/workspace/$p" ;;
  esac

  local resolved
  if resolved=$(realpath "$p" 2>/dev/null); then
    :
  else
    resolved=$(realpath -m "$p" 2>/dev/null) || resolved="$p"
  fi

  case "$resolved" in
    /workspace/repos/*) return 0 ;;
  esac
  return 1
}

# Validates a glob pattern. Only blocks absolute patterns outside scope.
# Relative patterns (e.g. **/*.py) are safe since they search from cwd.
check_pattern() {
  local p="$1"
  [ -z "$p" ] && return 0

  case "$p" in
    /*) ;;
    *) return 0 ;;
  esac

  local resolved
  resolved=$(realpath -m "$p" 2>/dev/null) || resolved="$p"

  case "$resolved" in
    /workspace/repos/*) return 0 ;;
  esac
  return 1
}

case "$tool" in
  Read)
    fp=$(echo "$input" | jq -r '.tool_input.file_path // empty')
    if ! check_path "$fp"; then
      echo "Blocked: read outside /workspace/repos/" >&2
      exit 2
    fi
    ;;
  Grep)
    gp=$(echo "$input" | jq -r '.tool_input.path // empty')
    if ! check_path "$gp"; then
      echo "Blocked: grep outside /workspace/repos/" >&2
      exit 2
    fi
    ;;
  Glob)
    gpath=$(echo "$input" | jq -r '.tool_input.path // empty')
    gpat=$(echo "$input" | jq -r '.tool_input.pattern // empty')
    if ! check_path "$gpath"; then
      echo "Blocked: glob path outside /workspace/repos/" >&2
      exit 2
    fi
    if ! check_pattern "$gpat"; then
      echo "Blocked: glob pattern outside /workspace/repos/" >&2
      exit 2
    fi
    ;;
esac

exit 0
