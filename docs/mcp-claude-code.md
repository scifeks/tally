# Claude Code Triage Backend

This document covers Claude Code-specific setup and runtime behavior for
Tally's automated triage workflow. For the generic triage command model, see
[MCP Triage System](./mcp.md).

## Prerequisites

Claude Code must be installed and the `claude` binary must be on your `PATH`.
Verify with:

```bash
claude --version
```

Claude Code also requires an Anthropic API key:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

If Claude Code is not installed, follow Anthropic's installation guidance.

## Runtime behavior

When `triage_agent_provider` is `"claude_code"`, Tally:

- generates a temporary `.mcp.json` for the session
- launches `claude` as a non-interactive subprocess from the Tally app root
- passes the triage prompt over stdin
- sets `TALLY_TRIAGED_BY=claudecode` for MCP-side persistence

Claude discovers the MCP server through `.mcp.json` in its working directory.
Tally owns that file's lifecycle and removes it automatically when the session
ends.

## Safety controls

The Claude adapter keeps the current non-interactive safety posture:

- `--dangerously-skip-permissions`
- `--disallowedTools Bash,Write,Edit,MultiEdit,WebFetch,WebSearch`

This allows Claude to use the Tally MCP tools and read local files needed for
triage, while still blocking arbitrary shell execution, file writes, and web
access.

## Troubleshooting

### Claude runtime missing

Verify:

```bash
claude --version
```

If this fails, install Claude Code and ensure the binary is on your `PATH`.

### Claude session makes no MCP calls

This usually means Claude did not discover the generated `.mcp.json` from the
session working directory. Run triage through the normal Tally entrypoints from
the Tally application root rather than invoking subprocesses from another
directory.

### Claude exits without updates

Check `tool_audit_log` first. If reads succeeded but no update call was made,
retry with a smaller `mcp_batch_size` to reduce per-session workload.
