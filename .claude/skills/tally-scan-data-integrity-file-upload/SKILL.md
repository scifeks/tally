---
name: tally-scan-data-integrity-file-upload
description: >
  Scan the target repo for unrestricted file upload defects. Detects
  upload handlers that save files without validating file extension,
  MIME type, or content. Emits findings shaped for Tally MCP submission
  (rule_id `data_integrity.file_upload`, CWE-434, severity high). Invoke
  when the user says "file upload", "unrestricted upload", "check for file
  upload vulnerabilities", or when dispatched by `tally-scan-external`.
---

# Tally scanner: Unrestricted file upload

Detects sinks where uploaded files reach storage without validation of
extension, MIME type, or content. Runs per-file in the target repo (as
dispatched by the `tally-scan-external` orchestrator, or standalone when
the user invokes this skill directly). Emits a JSON list of findings; the
orchestrator or the user submits them to Tally through the `submit_finding`
MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `data_integrity.file_upload` |
| Primary CWE | `CWE-434` |
| OWASP 2025 category | `Software or Data Integrity Failures` |
| Default severity | `high` |
| Parent label (dedup) | `UnrestrictedFileUpload` |


## Detection matrix

### Python

- **Flask request.files save without validation**: a handler that calls
  `request.files[].save()` without checking the filename extension or
  verifying the file content type before storing.
- **Django UploadedFile without FileExtensionValidator**: a model or form
  field that accepts `request.FILES[]` but does not apply
  `FileExtensionValidator` or magic-byte validation.
- **FastAPI UploadFile to disk without type check**: an endpoint that
  accepts an `UploadFile` parameter and writes it to disk (via
  `shutil.copyfile`, `.read().write()`, etc.) without validating the
  extension or MIME type.

Read `references/python.md` for vulnerable-vs-safe code patterns.

### PHP

- **move_uploaded_file without MIME allowlist**: a handler that calls
  `move_uploaded_file($_FILES['field']['tmp_name'], ...)` without
  checking the file extension or verifying MIME type via `finfo_file`.
- **Laravel storeAs without mimes validation**: a flow calling
  `$request->file()->store()` or `storeAs()` without `mimes` or
  `mimetypes` validation rules in the request's validate call.
- **Symfony UploadedFile->move without extension check**: a form handler
  that calls `UploadedFile->move()` without validating the extension
  against an allowlist or checking `guessExtension()`.
- **Direct $_FILES write without allowlist**: code that writes
  `$_FILES['file']['tmp_name']` content directly without checking the
  file extension or magic bytes.

Read `references/php.md` for vulnerable-vs-safe code patterns.

### JavaScript

- **Express + multer with no fileFilter**: middleware that configures
  `multer()` without a `fileFilter` callback to validate extension or
  MIME type.
- **Express + express-fileupload calling .mv() without checks**: code that
  uses `.mv()` to save an uploaded file without validating the extension
  or MIME type.
- **Koa + koa-body / formidable saving files unvalidated**: handlers that
  accept uploaded files and write them to disk without type validation.

Read `references/javascript.md` for vulnerable-vs-safe code patterns.

### TypeScript

- **NestJS @UploadedFile without ParseFilePipe validators**: an endpoint
  that accepts an `@UploadedFile()` parameter without `ParseFilePipe`
  validators such as `FileTypeValidator` or `MaxFileSizeValidator`.
- **Express typed + multer without fileFilter**: TypeScript/Express code
  using multer without a `fileFilter` callback.
- **Fastify + @fastify/multipart without content-type check**: routes that
  accept multipart uploads and write files without validating the
  Content-Type header or file extension.

Read `references/typescript.md` for vulnerable-vs-safe code patterns.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the save or store call.
- `meta.code_snippet`: 2-6 lines of source containing the upload sink.
- `meta.reasoning`: one sentence explaining why the upload handler lacks
  validation at this location.
- When the upload source is in the same file: `meta.taint_source` naming
  the request field or handler parameter that provides the uploaded file.

Set `confidence`:

- `confirmed` when the file is saved without any extension or MIME
  validation in the visible code path.
- `probable` when the upload sink is present but validation may occur
  upstream (middleware, decorator, or a form validator not visible in the
  immediate code).
- `potential` when the handler processes file uploads but the save call is
  not clearly visible in the immediate scope.

## Output payload skeleton

Emit one JSON object per finding with these fixed fields for
`data_integrity.file_upload`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing upload sink and attacker impact>",
  "severity": "high",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-434"],
  "finding_type": ["vulnerability"],
  "rule_id": "data_integrity.file_upload",
  "meta": {
    "title": "<e.g. 'Unrestricted upload in profile handler'>",
    "owasp_name": "Software or Data Integrity Failures",
    "remediation": "<per-finding remediation guidance>",
    "code_snippet": "<2-6 lines of source containing the save call>",
    "taint_source": "<request field or handler parameter if
      traceable>",
    "reasoning": "<one sentence explaining the missing validation>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for the full
field list and validator behavior.

## Remediation guidance for the scanner

Write `meta.remediation` inline based on the actual library
observed in the code. Examples of good remediation strings:

- **Flask**: `Validate the extension against an allowlist using
  werkzeug.utils.secure_filename() and check the file's magic bytes with
  python-magic before calling save().`
- **Django**: `Add FileExtensionValidator to the model field or form
  field. Check magic bytes with python-magic rather than trusting the
  Content-Type header.`
- **PHP native**: `Check the extension against an allowlist and verify the
  MIME type with finfo_file() on the tmp_name. Do not trust
  $_FILES['type'] because the client controls it.`
- **Laravel**: `Add validation rules: $request->validate(['file' =>
  'required|file|mimes:pdf,jpg,png|max:2048']). The mimes rule checks the
  file content, not only the extension.`
- **multer**: `Configure a fileFilter callback that checks the MIME type
  and extension against an allowlist. Set limits.fileSize to cap upload
  size.`
- **NestJS**: `Add ParseFilePipe with FileTypeValidator and
  MaxFileSizeValidator to the @UploadedFile() parameter.`

Keep it two to four sentences. Vague guidance ("validate the file") is
worse than no guidance.

## Common false positives

- **Allowlist validation upstream**: handlers where extension allowlist
  validation is applied in middleware, a form validator, or a decorator,
  even if the immediate save call has no explicit check.
- **Image re-encoding**: upload handlers that re-encode the image
  (e.g., PIL `Image.open().save()`) neutralize embedded payloads and are
  safe regardless of the input extension.
- **Admin-only routes**: upload endpoints gated by strong authorization
  checks that restrict access to administrators. Flag the handler but
  adjust confidence down.
- **Test fixtures and seed scripts**: upload handlers in CLI commands or
  test utilities that populate the database without validation. Flag but
  adjust confidence to `potential`.

## References

- `references/python.md`: Python patterns for Flask, Django, FastAPI.
- `references/php.md`: PHP patterns for native handlers, Laravel, Symfony.
- `references/javascript.md`: Node patterns for multer, express-fileupload,
  formidable, koa-body.
- `references/typescript.md`: TypeScript patterns for NestJS, Fastify,
  multer (typed).
