---
name: tally-scan-misconfig-error-message-exposure
description: >
  Scan the target repo for sensitive data exposure through error messages
  and exception handling. Detects HTTP responses that leak exception
  messages, stack traces, database error details, or internal error data to
  users. Emits findings shaped for Tally MCP submission (rule_id
  `misconfig.error_message_exposure`, CWE-209, CWE-200, severity medium).
  Invoke when the user says "error message exposure", "error details leak",
  "stack trace exposure", "check for error message disclosure", or when
  dispatched by `tally-scan-external`.
---

# Tally scanner: sensitive data in error messages

Detects code that leaks sensitive error details in HTTP responses. Targets
exception handlers, error pages, and catch blocks that return exception
messages, stack traces, or internal error information to users. Runs
per-file in the target repo (as dispatched by the `tally-scan-external`
orchestrator, or standalone when the user invokes this skill directly).
Emits a JSON list of findings; the orchestrator or the user submits them
to Tally through the `submit_finding` MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `misconfig.error_message_exposure` |
| Primary CWE | `CWE-209` |
| Secondary CWE | `CWE-200` |
| OWASP 2025 category | `Security Misconfiguration` |
| Default severity | `medium` |
| Parent label (dedup) | `ErrorMessageExposure` |


## Detection matrix

### Python

Read `references/python.md` for vulnerable-vs-safe snippets.

Detect these sink categories:

- **Django error views**: returning exception strings or stack traces in
  response bodies.
- **Flask error handlers**: returning exception messages or trace data in
  responses.
- **FastAPI exception handlers**: custom handlers returning full exception
  text to the client.
- **Catch blocks**: bare exception handlers returning error data to
  responses.

### PHP

Read `references/php.md` for vulnerable-vs-safe snippets.

Detect these sink categories:

- **display_errors setting**: ini_set enabling error output to the client.
- **Custom exception handlers**: handlers returning exception messages or
  traces in responses.
- **Laravel exception rendering**: returning exception details in responses
  or abort messages.

### JavaScript

Read `references/javascript.md` for vulnerable-vs-safe snippets.

Detect these sink categories:

- **Express error middleware**: error middleware returning err.stack or
  err.message in responses.
- **Catch blocks**: exception handlers in route handlers returning error
  details.
- **Koa error handling**: error handlers returning error messages or stacks.
- **Fastify error handlers**: custom error handlers returning internal error
  details.

### TypeScript

Read `references/typescript.md` for vulnerable-vs-safe snippets.

Detect these sink categories:

- **NestJS exception filters**: filters returning full exception objects or
  internal messages.
- **Express error middleware (typed)**: typed handlers returning err.stack or
  err.message.
- **Custom error DTOs**: response objects including stack traces or internal
  error messages.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the error handler or catch block.
- `meta.code_snippet`: 2-6 lines of source containing the handler logic.
- `meta.reasoning`: one sentence explaining why the handler leaks sensitive
  data.
- When the error response is constructed in the same file:
  `meta.taint_source` naming the exception variable or error object.

Set `confidence`:

- `confirmed` when the code path returns an exception message or stack
  trace directly in the response body, visible in the same file.
- `probable` when the error handler pattern matches but the exact response
  construction is in a helper function or framework method.
- `potential` when the error handling pattern is suspicious but the
  exposure is inferred from the exception handler's presence.

## Output payload skeleton

Emit one JSON object per finding with these fixed fields for
`misconfig.error_message_exposure`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing the handler, what data it exposes,
  and why an attacker can learn from the error message>",
  "severity": "medium",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-209", "CWE-200"],
  "finding_type": ["misconfiguration"],
  "rule_id": "misconfig.error_message_exposure",
  "meta": {
    "title": "<short human title, e.g. 'Error message exposure in Django
    exception handler'>",
    "owasp_name": "Security Misconfiguration",
    "remediation": "<per-finding; see remediation guidance
    below>",
    "code_snippet": "<2-6 lines of source containing the handler>",
    "taint_source": "<exception variable or error object name, when
    traceable>",
    "reasoning": "<one sentence explaining what sensitive data is exposed>"
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

- **Development-only error handlers**: error handlers guarded by
  `if app.debug`, `if settings.DEBUG`, `NODE_ENV !== 'production'`, or
  similar conditional that ensures the handler only runs in development.
- **Logging statements**: error messages written to log files or logging
  streams (not to HTTP responses). Logging the full exception server-side
  is safe.
- **Custom error pages**: HTML pages that return user-friendly error
  messages without exposing internal exception details.
- **Validation error messages**: responses that describe input validation
  failures (e.g., "Username must be 3-20 characters"). These describe user
  input constraints, not internal state.
- **Test files**: test files that intentionally assert on exception
  messages or stack trace content for testing purposes.
- **Application-defined error codes**: API responses that return
  application-specific error codes or messages (e.g., `{"error_code":
  404, "message": "Resource not found"}`), not exception internals.
- **Safe status text**: HTTP status text like "500 Internal Server Error"
  without additional details is safe.

## References

- `references/python.md`: Python patterns for Django, Flask, FastAPI error
  handling.
- `references/php.md`: PHP patterns for display_errors, custom exception
  handlers, Laravel, WordPress.
- `references/javascript.md`: Node patterns for Express, Koa, Fastify error
  middleware.
- `references/typescript.md`: TypeScript patterns for NestJS, Express with
  typed error handling.
