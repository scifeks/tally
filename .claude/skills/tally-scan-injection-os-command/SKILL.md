---
name: tally-scan-injection-os-command
description: >
  Scan the target repo for OS command injection defects. Detects shell
  commands executed with user input, unsafe subprocess calls with
  shell=True, shell_exec and exec in PHP, and child_process.exec in
  Node.js. Emits findings shaped for Tally MCP submission (rule_id
  `injection.os_command`, CWE-78, severity critical). Invoke when the
  user says "command injection", "shell injection", "check for OS command
  injection", or when dispatched by `tally-scan-external`.
---

# Tally scanner: OS command injection

Detects sinks where user-controlled data reaches a shell interpreter
without proper escaping or whitelisting. Runs per-file in the target repo
(as dispatched by the `tally-scan-external` orchestrator, or standalone
when the user invokes this skill directly). Emits a JSON list of findings;
the orchestrator or the user submits them to Tally through the
`submit_finding` MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `injection.os_command` |
| Primary CWE | `CWE-78` |
| Secondary CWE | `CWE-77` |
| OWASP 2025 category | `Injection` |
| Default severity | `critical` |
| Parent label (dedup) | `CommandInjection` |


## Detection matrix

### Python

Read `references/python.md` for vulnerable-vs-safe snippets.

Detect these sink categories:

- **os module functions**: direct shell execution via system and popen calls.
- **subprocess with shell interpretation**: call, Popen, run, or
  check_output with shell parameter enabled.
- **String-based command construction**: passing user-derived strings
  instead of argument arrays to process spawning functions.

### PHP

Read `references/php.md` for vulnerable-vs-safe snippets.

Detect these sink categories:

- **Direct shell execution functions**: exec, system, passthru, shell_exec,
  proc_open, popen.
- **Unsafe argument handling**: passing user input without escaping or
  parameterization to any shell execution function.
- **Backtick operators**: executing commands via shell metacharacters.

### JavaScript

Read `references/javascript.md` for vulnerable-vs-safe snippets.

Detect these sink categories:

- **exec and execSync**: functions that invoke the shell interpreter
  directly.
- **spawn with shell flag**: spawning a process with shell metacharacter
  interpretation enabled.
- **User input in command strings**: user-controlled data passed as the
  command argument rather than in an argument array.

### TypeScript

Read `references/typescript.md` for vulnerable-vs-safe snippets.

Detect these sink categories:

- **Same as JavaScript**: command injection patterns are identical on the
  Node.js runtime.
- **execa library**: wrapper around child_process with identical
  vulnerabilities when shell interpretation is enabled.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the sink call.
- `meta.code_snippet`: 2-6 lines of source containing the sink.
- `meta.reasoning`: one sentence explaining why the pattern is a command
  injection at this location.
- When the taint source is in the same file:
  `meta.taint_source` naming the request parameter or upstream variable
  that reaches the sink.

Set `confidence`:

- `confirmed` when a taint source is traced from a request handler to the
  sink in the same file, or through a same-file helper.
- `probable` when the sink pattern matches and the value is clearly a
  variable (not a constant), but the source is inferred.
- `potential` when the sink is suspicious but the value is not obviously
  user-controlled.

## Output payload skeleton

Emit one JSON object per finding with these fixed fields for
`injection.os_command`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing the sink, the source, and what an attacker can do>",
  "severity": "critical",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-78", "CWE-77"],
  "finding_type": ["vulnerability"],
  "rule_id": "injection.os_command",
  "meta": {
    "title": "<short human title, e.g. 'OS command injection via os.system'>",
    "owasp_name": "Injection",
    "remediation": "<per-finding; see remediation guidance below>",
    "code_snippet": "<2-6 lines of source containing the sink>",
    "taint_source": "<request parameter or upstream variable, when traceable>",
    "reasoning": "<one sentence explaining the defect at this location>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for the full
field list and validator behavior.

## Remediation guidance for the scanner

Write `meta.remediation` inline based on the actual library
observed in the code. Use the safe patterns from the per-language
reference files to write specific, actionable remediation.

- Name the library and its specific safe API
- Show the exact placeholder style or query builder method
- Keep it two to four sentences

## Common false positives

- **`subprocess.run()` with `shell=False` and argument list**: `run(['ls',
  '-la', path], shell=False)` is safe regardless of what `path` contains.
- **`subprocess.call()` with `shell=False`**: safe by default when
  `shell=False` is explicit or omitted.
- **`child_process.execFile()` with argument array**: `execFile('ls',
  [dir])` is safe; the second argument is never interpreted as a shell
  command.
- **`escapeshellarg()` in PHP**: wrapping each argument protects against
  injection. Confirm the entire command uses `escapeshellarg()` for every
  user-derived component.
- **Constants and enums**: interpolation of module-level constants or enum
  values with no user reachability is safe. Confirm the value is not later
  reassigned from a request.
- **Hardcoded commands with no user input**: `os.system('ls -la')` with a
  literal string is safe.

## References

- `references/python.md`: Python patterns for os, subprocess, and safe
  alternatives.
- `references/php.md`: PHP patterns for exec, system, passthru,
  shell_exec, and `escapeshellarg()`.
- `references/javascript.md`: Node.js patterns for child_process module.
- `references/typescript.md`: TypeScript patterns for child_process and
  execa.
