#!/bin/bash
set -u
TOOL_CMD=("$@")
while IFS= read -r timeout_secs && IFS= read -r b64_prompt; do
    prompt=$(printf '%s' "$b64_prompt" | base64 -d)
    output=$(printf '%s' "$prompt" | timeout -k 5 "$timeout_secs" "${TOOL_CMD[@]}" 2>/tmp/relay_stderr)
    rc=$?
    stderr=$(cat /tmp/relay_stderr 2>/dev/null || true)
    b64_out=$(printf '%s' "$output" | base64 -w 0)
    b64_err=$(printf '%s' "$stderr" | base64 -w 0)
    printf '{"rc":%d,"out":"%s","err":"%s"}\n' "$rc" "$b64_out" "$b64_err"
done
