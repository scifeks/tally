---
name: tally-scan-misconfig-insecure-file-permissions
description: >
  Scan the target repo for insecure file permissions on sensitive files.
  Detects overly permissive chmod operations, world-readable credentials
  and config files, predictable temp files, and race conditions in file
  creation. Emits findings shaped for Tally MCP submission (rule_id
  `misconfig.insecure_file_permissions`, CWE-276, severity medium).
  Invoke when the user says "file permissions", "chmod", "insecure
  permissions", or when dispatched by `tally-scan-external`.
---

# Tally scanner: insecure file permissions

Detects file permission weaknesses that expose sensitive data or enable
exploitation through race conditions. Recognizes overly permissive chmod
calls, temp file creation without proper restrictions, and patterns that
leave credential files world-readable. Runs per-file in the target repo
(as dispatched by the `tally-scan-external` orchestrator, or standalone
when the user invokes this skill directly). Emits a JSON list of findings;
the orchestrator or the user submits them to Tally through the
`submit_finding` MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `misconfig.insecure_file_permissions` |
| Primary CWE | `CWE-276` |
| Secondary CWE | `CWE-732` |
| OWASP 2025 category | `Security Misconfiguration` |
| Default severity | `medium` |
| Parent label (dedup) | `File Permissions` |

Source: `docs/roadmap/TAL-148/taxonomy.md`. CWE-276 (Incorrect Default
Permissions) and CWE-732 (Incorrect Permission Assignment) are the primary
weaknesses for file permission misconfigurations.

## Detection matrix

### Python

- **os.chmod with overly permissive mode**: `os.chmod(path, 0o777)` or
  `0o666` on credential, config, or secret files; any mode granting
  world-write or world-read to sensitive paths.
- **os.umask to world access**: `os.umask(0)` or `os.umask(0o000)` which
  removes all permission restrictions; subsequent file creation operations
  lack necessary restrictions.
- **open() for secrets without mode restriction**: `open(path, 'w')` or
  `open(path, 'a')` writing to credential or config files without setting
  a restrictive mode parameter; file is created with default umask-derived
  permissions which may be world-readable.
- **tempfile.mktemp() usage**: `tempfile.mktemp()` which generates
  predictable names vulnerable to symlink attacks and race conditions.
- **tempfile.NamedTemporaryFile with delete=False**: temp file is created
  without explicit restrictive mode, leaving it world-readable on some
  systems; file persists on disk after process exit.

Defer to `references/python.md` for vulnerable-vs-safe snippets.

### PHP

- **chmod with overly permissive mode**: `chmod($file, 0777)` or `0666`
  on config, secret, or credential files.
- **file_put_contents without umask**: writing credentials or config data
  to a file without setting a restrictive umask beforehand; file inherits
  default permissions which may be world-readable.
- **tmpfile() usage patterns**: `tmpfile()` creates a file in a system temp
  directory; the file may be world-readable depending on system
  configuration and temp directory permissions.
- **Config files written with permissive defaults**: application code that
  writes `.env`, database credentials, or API keys without explicitly
  setting restrictive file permissions.

Defer to `references/php.md` for vulnerable-vs-safe snippets.

### JavaScript

- **fs.writeFileSync with overly permissive mode**: `fs.writeFileSync(path,
  data, {mode: 0o777})` or `{mode: 0o666}` on credential or config files.
- **fs.chmodSync with overly permissive mode**: `fs.chmodSync(path, 0o777)`
  or `0o666` on sensitive files.
- **fs.mkdtempSync without restrictive mode**: creating a temp directory
  without specifying a restrictive mode, resulting in world-readable or
  world-writable temp paths.
- **Secrets written without permission control**: writing API keys,
  passwords, or credentials to files using `fs.writeFileSync()` or
  `fs.promises.writeFile()` without setting the mode option to restrict
  access.

Defer to `references/javascript.md` for vulnerable-vs-safe snippets.

### TypeScript

- **fs.writeFileSync with overly permissive mode**: same pattern as
  JavaScript with `{mode: 0o777}` or `{mode: 0o666}`.
- **fs.chmodSync with overly permissive mode**: `fs.chmodSync(path, 0o777)`
  or `0o666`.
- **fs.mkdtempSync without restrictive mode**: creating temp directories
  without mode restrictions.
- **Secrets written to files**: TypeScript files writing credentials,
  tokens, or secrets without setting restrictive file permissions via the
  mode option.

Defer to `references/typescript.md` for vulnerable-vs-safe snippets.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the file operation that sets or
  creates a file with insecure permissions.
- `meta.code_snippet`: 2-6 lines of source containing the insecure
  operation.
- `meta.reasoning`: one sentence explaining why the permission is insecure
  and the data risk at this location.
- When the file path is derived from user input or an environment variable:
  `meta.taint_source` naming the upstream variable.

Set `confidence`:

- `confirmed` when the insecure permission is hardcoded (e.g.,
  `os.chmod(path, 0o777)`) or when using functions like `tempfile.mktemp()`
  that are inherently unsafe.
- `probable` when the permission pattern is overly permissive but is
  conditionally applied based on an environment variable or configuration
  with no validation.
- `potential` when the permission is set on a file whose purpose is
  ambiguous (e.g., a file whose name does not clearly indicate whether it
  holds secrets).

## Output payload skeleton

Emit one JSON object per finding with these fixed fields for
`misconfig.insecure_file_permissions`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing the insecure permission, the file
  purpose, and the data exposure risk>",
  "severity": "medium",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-276", "CWE-732"],
  "finding_type": ["misconfiguration"],
  "rule_id": "misconfig.insecure_file_permissions",
  "meta": {
    "title": "<short human title, e.g. 'Overly permissive chmod on
    credential file'>",
    "owasp_name": "Security Misconfiguration",
    "remediation": "<per-finding remediation specific to the operation
    and file type; see remediation guidance below>",
    "code_snippet": "<2-6 lines of source containing the insecure
    permission operation>",
    "reasoning": "<one sentence explaining the data exposure or attack
    risk at this location>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for the full
field list and validator behavior.

## Remediation guidance for the scanner

Per D19, write `meta.remediation` inline based on the actual operation
observed in the code. Examples of good remediation strings:

- **Python chmod**: `Replace os.chmod(path, 0o777) with os.chmod(path,
  0o600) to restrict read/write to the owner only. For config files, use
  0o640 if group access is needed.`
- **Python os.umask**: `Remove os.umask(0) call. Instead, set restrictive
  permissions explicitly on each sensitive file with os.chmod(path, 0o600).`
- **Python open() for secrets**: `Add the mode parameter to open():
  open(path, 'w', mode=0o600) to restrict the file to owner-only access.`
- **Python tempfile.mktemp()**: `Replace tempfile.mktemp() with
  tempfile.NamedTemporaryFile(delete=False, mode=0o600) to create a
  cryptographically unique temp file with owner-only permissions.`
- **PHP chmod**: `Replace chmod($file, 0777) with chmod($file, 0600) to
  restrict read/write to the owner only. For shared files, use 0640 if
  group access is required.`
- **PHP file_put_contents**: `Before writing credentials, set a restrictive
  umask: $old_umask = umask(0o077); file_put_contents($path, $data);
  umask($old_umask);. Restore the original umask after the operation.`
- **JavaScript fs.writeFileSync**: `Add the mode option to restrict
  permissions: fs.writeFileSync(path, data, {mode: 0o600}) for
  owner-only access.`
- **JavaScript fs.mkdtempSync**: `Specify a restrictive mode:
  fs.mkdtempSync(path, {recursive: true, mode: 0o700}) to restrict the
  temp directory to owner-only access.`

Keep it two to four sentences. Vague guidance ("use restrictive
permissions") is worse than no guidance.

## Common false positives

- **Public static asset directories**: files in `public/`, `static/`,
  `dist/`, or `build/` directories intentionally world-readable are safe
  and must not be flagged.
- **Temp files in properly secured temp directories**: files created in
  `/tmp`, `tempdir()`, or OS-provided temp directories that are already
  secured by the OS are generally safe; flag only if the application adds
  extra world-readable permissions on top.
- **Log files**: log files (typically `*.log`) often need to be group- or
  world-readable for monitoring agents; flag only if the permissions expose
  sensitive data like passwords or tokens within the logs themselves.
- **Docker and container environments**: file permissions are less relevant
  in containerized environments where user IDs are isolated; flag only
  obvious world-write cases (0o777) or when credentials are exposed.
- **Test fixtures and mock data**: files in test directories (`tests/`,
  `__tests__/`, `spec/`) used for unit or integration testing are safe and
  must not be flagged.
- **Build artifacts and generated files**: compiled binaries, `.class` files,
  `.pyc`, `node_modules/`, and other build outputs are safe and must not be
  flagged.
- **Files with conditionally set permissions**: `os.chmod(path,
  os.getenv('FILE_MODE', '0o600'))` where the default is safe are safe
  patterns.
- **Symlinks and special files**: `chmod` on symlinks, device files, or
  pipes has no effect; these are not security risks and must not be flagged.

## References

- `references/python.md`: Python patterns for os.chmod, os.umask, open(),
  tempfile.
- `references/php.md`: PHP patterns for chmod, file_put_contents, tmpfile,
  umask.
- `references/javascript.md`: Node patterns for fs.writeFileSync,
  fs.chmodSync, fs.mkdtempSync.
- `references/typescript.md`: TypeScript patterns for fs operations with
  type-safe interfaces.
