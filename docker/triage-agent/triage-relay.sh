#!/bin/bash
# Usage: triage-relay [--system-prompt-flag FLAG] CMD...
# Per request reads three lines: timeout seconds, base64 system prompt (may be
# empty), base64 user prompt. A non-empty system prompt is passed to CMD as
# FLAG's value so trusted instructions stay out of the user message.
set -u
SYSTEM_FLAG=""
if [ "${1:-}" = "--system-prompt-flag" ]; then
    SYSTEM_FLAG="$2"
    shift 2
fi
TOOL_CMD=("$@")
while IFS= read -r timeout_secs && IFS= read -r b64_system && IFS= read -r b64_prompt; do
    cmd=("${TOOL_CMD[@]}")
    if [ -n "$b64_system" ]; then
        if [ -z "$SYSTEM_FLAG" ]; then
            # Refuse rather than drop the instructions and run on data alone.
            b64_err=$(printf 'system prompt sent but relay has no --system-prompt-flag' | base64 -w 0)
            printf '{"rc":2,"out":"","err":"%s"}\n' "$b64_err"
            continue
        fi
        cmd+=("$SYSTEM_FLAG" "$(printf '%s' "$b64_system" | base64 -d)")
    fi
    prompt=$(printf '%s' "$b64_prompt" | base64 -d)
    output=$(printf '%s' "$prompt" | timeout -k 5 "$timeout_secs" "${cmd[@]}" 2>"${TMPDIR:-/tmp}/relay_stderr")
    rc=$?
    stderr=$(cat "${TMPDIR:-/tmp}/relay_stderr" 2>/dev/null || true)
    b64_out=$(printf '%s' "$output" | base64 -w 0)
    b64_err=$(printf '%s' "$stderr" | base64 -w 0)
    printf '{"rc":%d,"out":"%s","err":"%s"}\n' "$rc" "$b64_out" "$b64_err"
done
