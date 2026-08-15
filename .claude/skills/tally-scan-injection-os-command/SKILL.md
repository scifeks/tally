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

Source: `docs/roadmap/TAL-148/taxonomy.md` T3 row 4.

## Detection matrix

### Python

- **`os.system()` with user input**: passes a command string directly to
  the shell. The argument is evaluated by the shell interpreter.
- **`os.popen()` with user input**: opens a pipe to a shell command.
- **`subprocess.call()` with `shell=True`**: executes a string command via
  the shell when `shell=True` is set.
- **`subprocess.Popen()` with `shell=True`**: spawns a process with shell
  interpretation of the command string.
- **`subprocess.run()` with `shell=True`**: runs a command with shell
  interpretation.
- **`subprocess.check_output()` with `shell=True` and user input**: same
  vulnerability as `run` and `Popen`.

The key signal is `shell=True` combined with a user-derived string instead
of a list of arguments.

Defer to `references/python.md` for vulnerable-vs-safe snippets.

### PHP

- **`exec($userInput)`**: executes a shell command and returns output.
- **`system($userInput)`**: executes a shell command and outputs result
  directly.
- **`passthru($userInput)`**: executes a shell command and passes output
  directly to stdout.
- **`shell_exec($userInput)` or backtick operator**: executes a shell
  command via backticks.
- **`proc_open($userInput, ...)`**: opens a process with a command string.
- **`popen($userInput, ...)`**: opens a process pipe.

Safe forms wrap arguments with `escapeshellarg()` per argument or use
parameter arrays in newer PHP versions.

Defer to `references/php.md` for vulnerable-vs-safe snippets.

### JavaScript

- **`child_process.exec(userInput)`**: executes a string command via
  `/bin/sh` (or `cmd.exe` on Windows).
- **`child_process.execSync(userInput)`**: synchronous version of `exec`.
- **`child_process.spawn('sh', ['-c', userInput])`**: spawns a shell with
  the user input as a command.

Safe forms use `child_process.execFile()` with an argument array or
`spawn()` with array arguments (no `-c` flag).

Defer to `references/javascript.md` for vulnerable-vs-safe snippets.

### TypeScript

- **Same as JavaScript**: command injection patterns are identical on the
  Node.js runtime.
- **`execa` library with `shell: true` and user input**: wraps Node's
  child_process but the vulnerability is the same.

Defer to `references/typescript.md` for vulnerable-vs-safe snippets.

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
    "remediation": "<per-finding, per D19; see remediation guidance below>",
    "code_snippet": "<2-6 lines of source containing the sink>",
    "taint_source": "<request parameter or upstream variable, when traceable>",
    "reasoning": "<one sentence explaining the defect at this location>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for the full
field list and validator behavior.

## Remediation guidance for the scanner

Per D19, write `meta.remediation` inline based on the actual library
observed in the code. Examples of good remediation strings:

- **Python (subprocess)**: `Use `subprocess.run()` with a list of
  arguments and `shell=False`: `subprocess.run(['ls', '-la', user_path],
  shell=False)`. Never pass user input as part of the command string.`
- **Python (os module)**: `Avoid `os.system()` and `os.popen()`. Migrate
  to `subprocess.run()` with argument lists: `subprocess.run(['rm', '-f',
  filename], shell=False)`.`
- **PHP**: `Wrap each argument with `escapeshellarg()`: `exec('ls ' .
  escapeshellarg($dir))`. Better, refactor to use PHP functions directly
  (e.g., `scandir()` instead of shelling out).`
- **Node.js**: `Use `child_process.execFile()` with argument arrays:
  `execFile('ls', [userDir])`. Avoid `exec()` and `spawn('sh', ['-c',
  ...])` with user input.`

Keep it two to four sentences. Vague guidance ("use safe subprocess calls")
is worse than no guidance.

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
