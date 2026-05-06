# OpenCode Triage Backend

This document covers OpenCode-specific setup and runtime behavior for Tally's
automated triage workflow. For the generic triage command model, see
[MCP Triage System](./mcp.md).

## Prerequisites

OpenCode must be installed and the `opencode` binary must be available. Tally's
runtime probe prefers `~/.opencode/bin/opencode` and falls back to `PATH`.

Verify with:

```bash
opencode --version
```

The live Phase 4.2 validation used OpenCode `1.14.39`.

## Runtime behavior

When `triage_agent_provider` is `"open_code"`, Tally:

- generates a disposable `opencode.json` for the session
- points OpenCode at it with `OPENCODE_CONFIG`
- launches `opencode run --dir <app_root> --format json`
- passes the triage prompt over stdin
- sets `TALLY_TRIAGED_BY=opencode` for MCP-side persistence

Tally keeps `cwd=<app_root>` and also passes `--dir <app_root>` so session
directory handling stays explicit and stable.

OpenCode's JSON stdout is kept as diagnostic output only. Session success still
comes from MCP write side effects plus subprocess outcome, not model-output
parsing.

## Safety controls

The generated `opencode.json` carries a hardened minimum triage profile:

- deny `edit`
- deny `bash`
- deny `webfetch`
- allow filesystem reads
- deny filesystem writes
- allow only the Tally MCP namespace via `tally-mcp_*`

This keeps OpenCode aligned with the current triage safety posture: read and
analyze findings, but do not edit files, run arbitrary shell commands, or use
the network.

## Troubleshooting

### OpenCode runtime missing

Verify:

```bash
opencode --version
```

If this fails, install OpenCode or ensure the binary is available either at
`~/.opencode/bin/opencode` or on `PATH`.

### OpenCode session fails before MCP updates

Inspect the session's diagnostic stderr output and recent `tool_audit_log`
entries. If no update calls happened, the batch will be marked `incomplete` or
`failed` depending on the subprocess result.

### Permission profile errors

Tally writes explicit `read` and `write` permission maps into the generated
`opencode.json`. If a future OpenCode release changes that schema, start by
checking the generated config path from `OPENCODE_CONFIG` and comparing it
against the installed runtime's accepted format.
