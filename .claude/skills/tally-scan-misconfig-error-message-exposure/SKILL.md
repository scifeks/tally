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

Source: `docs/roadmap/TAL-148/taxonomy.md` T3 row 38.

## Detection matrix

### Python

- **Django error views**: custom error view functions returning
  `str(exception)` or `traceback.format_exc()` in the response body.
- **Django exception handlers**: exception handler decorators catching
  exceptions and returning `JsonResponse({"error": str(e)})` or similar.
- **Flask error handlers**: `@app.errorhandler` functions returning
  `str(e)` or `traceback.format_exc()` in the response body.
- **Flask catch blocks**: bare `except` blocks in route handlers returning
  the exception message directly to the client.
- **FastAPI exception handlers**: custom exception handlers in route
  handlers returning `{"detail": str(exc)}` with the full exception text.
- **FastAPI catch blocks**: catch blocks in route handlers exposing
  `exc.detail` or `str(exc)` in response bodies.

Defer to `references/python.md` for vulnerable-vs-safe snippets.

### PHP

- **display_errors setting**: `ini_set('display_errors', '1')` or
  `ini_set('display_errors', 'On')` in application code turns on error
  output to the client.
- **Custom exception handlers**: exception handler functions calling
  `$e->getMessage()`, `$e->getTraceAsString()`, or `$e->getTrace()` in
  response output.
- **Laravel exception rendering**: custom exception render methods
  returning exception details; `abort()` calls with sensitive messages
  that reach the response.
- **WordPress error output**: `wp_die()` called with database error
  messages or exception details.

Defer to `references/php.md` for vulnerable-vs-safe snippets.

### JavaScript

- **Express error middleware**: error middleware functions sending
  `err.stack` or `err.message` in the response body.
- **Express catch blocks**: unguarded `catch(err)` blocks in route
  handlers returning the full error object or `err.message`.
- **Koa error handling**: `ctx.body = err.message` or `ctx.body = err.stack`
  in error handlers or middleware.
- **Fastify error handlers**: custom error handlers returning internal
  error details in the response body.

Defer to `references/javascript.md` for vulnerable-vs-safe snippets.

### TypeScript

- **NestJS exception filters**: exception filters returning full exception
  objects or internal error messages in the response.
- **NestJS HttpException**: `HttpException` instantiated with internal
  error details as the message parameter.
- **Express error middleware (typed)**: typed error handlers sending
  `err.stack` or `err.message` in the response body.
- **Custom error DTOs**: data transfer objects that include stack traces
  or internal error messages serialized to the HTTP response.

Defer to `references/typescript.md` for vulnerable-vs-safe snippets.

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
    "remediation": "<per-finding, per D19; see remediation guidance
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

Per D19, write `meta.remediation` inline based on the actual library or
framework observed in the code. Examples of good remediation strings:

- **Django views**: `Return a generic error message to the user:
  JsonResponse({"error": "Internal server error"}, status=500). Log the
  full exception server-side with logger.exception() for debugging.`
- **Flask error handlers**: `In the error handler, return a generic
  message: return jsonify(error="Internal server error"), 500. Log the
  exception server-side with app.logger.exception().`
- **FastAPI routes**: `Remove the `str(exc)` from the response. Instead,
  return a generic message like {"detail": "Internal server error"}. Log
  exc server-side using the Python logging module or a structured logger.`
- **Express middleware**: `In the error middleware, send a generic message:
  res.status(500).json({error: "Internal server error"}). Log err.stack
  server-side with your logging library.`
- **PHP application code**: `Set display_errors = Off in production
  php.ini. In custom exception handlers, return a generic message and log
  the full exception server-side with error_log() or a PSR-3 logger.`
- **NestJS exception filters**: `In exception filters, return a generic
  HttpException with a user-safe message. Log the original exception
  server-side with the Logger service.`
- **Laravel**: `In the exception handler's render method, return a generic
  error response. Log the full exception using Log::error() or similar.`

Keep it two to four sentences. Vague guidance ("hide errors") is worse
than no guidance.

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
