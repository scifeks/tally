---
name: tally-scan-access-control-path-traversal
description: >
  Scan the target repo for path traversal defects. Detects file
  operations that construct paths from user input without normalization
  or base-directory containment checks, including `../` sequences
  reaching filesystem calls. Emits findings shaped for Tally MCP
  submission (rule_id `access_control.path_traversal`, CWE-22,
  severity high). Invoke when the user says "path traversal",
  "directory traversal", "LFI", "check for path traversal", or when
  dispatched by `tally-scan-external`.
---

# Tally scanner: Path traversal

Detects sinks where user-controlled data reaches a filesystem operation
without containment validation. Runs per-file in the target repo (as
dispatched by the `tally-scan-external` orchestrator, or standalone
when the user invokes this skill directly). Emits a JSON list of
findings; the orchestrator or the user submits them to Tally through
the `submit_finding` MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `access_control.path_traversal` |
| Primary CWE | `CWE-22` |
| OWASP 2025 category | `Broken Access Control` |
| Default severity | `high` |
| Parent label (dedup) | `PathTraversal` |


## Detection matrix

### Python

- **`os.path.join` without containment check**: a request-derived
  filename or path appended to a base directory via `os.path.join`,
  `pathlib.Path / operator`, or string concatenation, then passed to
  `open`, `os.stat`, `shutil.copy`, or other filesystem functions
  without resolving and validating the result stays within the base.
- **`pathlib.Path` without `.resolve()` containment**: user input
  spliced into a Path object, then accessed, without confirming the
  resolved path is relative to the base directory.
- **Flask `send_file` without `send_from_directory`**:
  `send_file(os.path.join(static_dir, request.args['file']))` allows
  traversal; safe form uses `send_from_directory(static_dir, filename)`.
- **`shutil.copy` with unsanitized target**: target filename built from
  user input without stripping `../` or checking the parent directory.
- **f-string path construction**: `open(f"{upload_dir}/{filename}")`
  where `filename` is request-sourced and unchecked.

Read `references/python.md` for vulnerable-vs-safe code patterns.

### PHP

- **Direct concatenation into file operations**:
  `file_get_contents($dir . '/' . $_GET['file'])` without realpath or
  containment validation.
- **`readfile` or `fopen` with request-sourced filename**: the filename
  appended to a base directory but not validated against traversal.
- **`include` or `require` with request-sourced template**: template
  path constructed from request data without checking containment.
- **Laravel `Storage::get` with unchecked path**:
  `Storage::get($request->input('path'))` without path validation.
- **`realpath` comparison**: file operations that call `realpath` but
  do not verify the result is within the base directory using
  `strpos($real, $base) === 0` or equivalent.

Read `references/php.md` for vulnerable-vs-safe code patterns.

### JavaScript

- **`fs.readFile` without containment**:
  `fs.readFile(path.join(dir, req.params.filename))` allows traversal
  via `../`; safe form validates the resolved path stays within `dir`.
- **`fs.createReadStream` without validation**: request-sourced path
  appended to a base directory, then passed to stream creation without
  containment check.
- **`res.sendFile` without normalization**:
  `res.sendFile(path.join(__dirname, req.params.path))` without
  validating the result; unsafe.
- **`fs.writeFile` with unsanitized filename**: destination built from
  request data without stripping traversal sequences or checking the
  parent directory.
- **String concatenation into file operations**:
  `fs.readFile(base + '/' + req.query.file)` without path validation.

Read `references/javascript.md` for vulnerable-vs-safe code patterns.

### TypeScript

- **`fs.promises.readFile` without containment check**:
  `fs.promises.readFile(path.resolve(base, userPath))` without
  validating the resolved path stays within base.
- **NestJS file upload handler with original filename**:
  `fs.writeFile(uploadDir + file.originalname, ...)` allows traversal
  via crafted filenames in the upload.
- **Same Node.js patterns as JavaScript** with typed equivalents.

Read `references/typescript.md` for vulnerable-vs-safe code patterns.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the filesystem operation (the
  sink).
- `meta.code_snippet`: 2-6 lines of source containing the sink.
- `meta.reasoning`: one sentence explaining why the pattern allows
  traversal at this location.
- When the taint source is in the same file:
  `meta.taint_source` naming the request parameter or upstream
  variable that reaches the sink.

Set `confidence`:

- `confirmed` when a taint source is traced from a request handler to
  the sink in the same file, or through a same-file helper.
- `probable` when the sink pattern matches and the value is clearly a
  variable (not a constant), but the source is inferred.
- `potential` when the sink is suspicious but the value is not
  obviously user-controlled.

## Output payload skeleton

Emit one JSON object per finding with these fixed fields for
`access_control.path_traversal`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing the sink, the source, and what an
    attacker can do>",
  "severity": "high",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-22"],
  "finding_type": ["vulnerability"],
  "rule_id": "access_control.path_traversal",
  "meta": {
    "title": "<short human title, e.g. 'Path traversal via
      unsanitized filename'>",
    "owasp_name": "Broken Access Control",
    "remediation": "<per-finding; see remediation guidance
      below>",
    "code_snippet": "<2-6 lines of source containing the sink>",
    "taint_source": "<request parameter or upstream variable, when
      traceable>",
    "reasoning": "<one sentence explaining the defect at this
      location>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for
the full field list and validator behavior.

## Remediation guidance for the scanner

Write `meta.remediation` inline based on the actual library or
framework observed in the code. Examples of good remediation strings:

- **Python `pathlib`**: `Resolve the full path and verify it is
  contained within the base: resolved = (Path(base) /
  user_input).resolve(); assert resolved.is_relative_to(base).`
- **Python `os.path`**: `Use realpath on the result and verify it
  starts with the base directory: real = os.path.realpath(
  os.path.join(base, user_input)); assert real.startswith(
  os.path.realpath(base)).`
- **PHP**: `Call realpath on the result and verify it starts with the
  base using strpos: $real = realpath($base . '/' . $file); if
  (strpos($real, realpath($base)) !== 0) abort(403);.`
- **Node.js**: `Resolve the path and verify it starts with the base:
  const resolved = path.resolve(base, input); if
  (!resolved.startsWith(path.resolve(base))) throw new Error
  ('Invalid path');.`
- **Flask**: `Use send_from_directory instead of send_file:
  from flask import send_from_directory; return send_from_directory
  (static_dir, filename); rather than send_file(os.path.join(
  static_dir, filename)).`

Keep it two to four sentences. Vague guidance ("validate the path")
is worse than no guidance.

## Common false positives

- **Paths with hardcoded sequences**: `open(
  os.path.join(safe_dir, 'static/file.txt'))` where the entire path
  is static; no traversal possible.
- **Paths from database lookups**: file paths constructed from a
  database row or row ID, not from request input; traversal risk is
  controlled upstream.
- **Paths using UUIDs or numeric IDs**: filenames like
  `uploads/{uuid4()}.txt` or `uploads/{user_id}.txt`; the filename
  cannot contain `../`.
- **Paths with `path.basename()` extraction**: `fs.readFile(
  path.join(dir, path.basename(req.params.file)))` strips directory
  components; traversal cannot occur.
- **Flask `send_from_directory`**: `send_from_directory(uploads_dir,
  filename)` handles containment internally; safe.
- **Paths with explicit filtering**: code that strips `../` sequences
  or validates the filename against a regex before splicing it into
  the path; safe by design.

## References

- `references/python.md`: Python patterns for `os.path`, `pathlib`,
  Flask, `shutil`.
- `references/php.md`: PHP patterns for filesystem functions, Laravel,
  realpath validation.
- `references/javascript.md`: Node patterns for `fs` module, `path`
  module, Express.
- `references/typescript.md`: TypeScript patterns for Node.js APIs with
  typed wrappers, NestJS file handling.
