---
name: tally-scan-design-logic-missing-exception-handling
description: >
  Scan the target repo for missing exception handling around
  security-critical operations. Detects auth checks, permission
  validations, rate limiters, and signature verifications that throw
  exceptions where the exception path allows the request to proceed
  (fail-open paths) instead of denying access. Also detects assert
  statements used for security validation (stripped in optimized mode)
  and exception handlers that silently swallow security-check failures.
  Emits findings shaped for Tally MCP submission (rule_id
  `design_logic.missing_exception_handling`, CWE-754, severity high).
  Invoke when the user says "missing exception handling", "fail-open",
  "exception bypass", "security check exception", or when dispatched by
  `tally-scan-external`.
---

# Tally scanner: Missing exception handling around security checks

Detects security-critical operations that can throw exceptions where
exception handlers allow the request to proceed instead of denying it.
Runs per-file in the target repo (as dispatched by the
`tally-scan-external` orchestrator, or standalone when the user invokes
this skill directly). Emits a JSON list of findings; the orchestrator or
the user submits them to Tally through the `submit_finding` MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `design_logic.missing_exception_handling` |
| Primary CWE | `CWE-754` |
| OWASP 2025 category | `Insecure Design` |
| Default severity | `high` |
| Parent label (dedup) | `MissingExceptionHandling` |

Source: `docs/roadmap/TAL-148/taxonomy.md` T3 row.

## Detection matrix

### Python

- **Middleware/decorator with fail-open except**: A decorator or
  middleware function wraps an auth check (database lookup, external
  provider call, permission validation) in try/except, then calls the
  next handler or returns a success response in the except block instead
  of raising or returning a 403.
- **Empty or silent catch**: `except Exception: pass`,
  `except: pass` wrapping a security validation. The exception is
  swallowed; the request proceeds.
- **Bare except clause**: `except:` (without `Exception` qualifier) that
  silences an exception from a security check.
- **Assert for security**: `assert condition, "error"` used to validate
  permissions, authentication, or rate limits. Assertions are stripped
  in `-O` and `-OO` optimization modes, causing the check to disappear.

Defer to `references/python.md` for vulnerable-vs-safe snippets.

### PHP

- **Laravel middleware fail-open**: In `handle()` method, the auth check
  is wrapped in try/catch with `return $next($request)` in the catch
  block. Request proceeds when auth throws.
- **Symfony security voter fail-open**: A `vote()` method catches an
  exception from a permission check and returns `ABSTAIN` or `ALLOW`
  instead of re-throwing or returning `DENY`.
- **Empty or logging-only catch**: `catch (Exception $e) { }` or
  `catch (Exception $e) { Log::error(...) }` wrapping a security
  operation. The failure is logged but the request proceeds.
- **Assertion for security**: `assert($condition)` used for permission
  checks. Can be disabled via `zend.assertions = -1`.

Defer to `references/php.md` for vulnerable-vs-safe snippets.

### JavaScript

- **Express middleware fail-open**: `next()` called in catch block after
  an auth check fails. Request proceeds to protected route.
- **Unhandled promise rejection in auth**: Promise-based auth check
  without `.catch()` rejection handler, or a catch that calls `next()`
  instead of `next(err)` or `res.status(401)`.
- **Missing error argument in next**: `next()` called instead of
  `next(err)` after an auth failure. Some Express versions allow the
  request to proceed if no error is passed.
- **Silent catch**: `try { auth(); } catch (e) { }` where the
  exception is swallowed and execution continues.

Defer to `references/javascript.md` for vulnerable-vs-safe snippets.

### TypeScript

- **NestJS guard with global exception filter fail-open**: A guard
  `canActivate()` throws on auth failure, but a global exception filter
  catches it and returns HTTP 200 instead of 401/403.
- **Async auth without await**: An async auth middleware's promise
  rejection does not block the synchronous `next()` call; the request
  proceeds before the promise settles.
- **Decorator wrapping permission check**: A permission-check decorator
  catches exceptions and defaults to allowing access instead of
  throwing.
- **Fastify hook with silent catch**: An `onRequest` hook throws on
  auth failure, but the catch block calls `done()` without an error,
  allowing the handler to execute.

Defer to `references/typescript.md` for vulnerable-vs-safe snippets.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the security check or exception
  handler.
- `meta.code_snippet`: 2-6 lines of source containing the check and the
  exception handler.
- `meta.reasoning`: one sentence explaining why this pattern allows a
  request to bypass security checks.
- When the security operation is traceable: `meta.taint_source` naming
  the protected resource or operation being validated.

Set `confidence`:

- `confirmed` when the fail-open path is explicit (a catch block calls
  next/return without denying).
- `probable` when the exception handler is present but its intent is
  unclear (logs the error but does not re-raise or return an error
  response).
- `potential` when an assert statement is used for security validation
  (might be stripped in production).

## Output payload skeleton

Emit one JSON object per finding with these fixed fields for
`design_logic.missing_exception_handling`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing the security check, the exception
  path, and how an attacker can bypass the check>",
  "severity": "high",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-754"],
  "finding_type": ["vulnerability"],
  "rule_id": "design_logic.missing_exception_handling",
  "meta": {
    "title": "<short human title, e.g. 'Auth check fails silently in
    middleware'>",
    "owasp_name": "Insecure Design",
    "remediation": "<per-finding, per D19; see remediation guidance
    below>",
    "code_snippet": "<2-6 lines of source containing the check and
    handler>",
    "reasoning": "<one sentence explaining how the exception path
    allows bypass>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for the
full field list and validator behavior.

## Remediation guidance for the scanner

Per D19, write `meta.remediation` inline based on the actual framework
observed in the code. Examples of good remediation strings:

- **Python Django middleware**: `In the except block, return an
  HttpResponseForbidden (403) or raise PermissionDenied. Never call the
  next middleware when the auth check fails.`
- **Python FastAPI dependency**: `Raise a 403 HTTPException instead of
  catching the exception silently. Wrap the dependency invocation with
  proper error handling at the handler level, not at the dependency
  level.`
- **PHP Laravel middleware**: `In the catch block, return response
  with status 403 or abort(403). Never return $next($request) when the
  auth check throws.`
- **JavaScript Express middleware**: `Call next(err) with the caught
  error, or return res.status(401).json({error: 'unauthorized'}). Never
  call next() without arguments after an auth failure.`
- **TypeScript NestJS**: `Verify that the global exception filter maps
  auth exceptions to 401/403 responses, not 200. Guards should throw
  UnauthorizedException or ForbiddenException, which the filter then
  converts to proper HTTP responses.`
- **Assertion security check**: `Replace the assert statement with an
  explicit if statement that raises/throws an exception. Assertions may
  be stripped in production builds; use raise/throw statements instead.`

Keep it two to four sentences. Vague guidance ("handle exceptions
properly") is worse than no guidance.

## Common false positives

- **Non-security exception handling**: Try/catch around logging,
  metrics, caching, or analytics where failure is acceptable and does
  not grant access. Exception handling for these is safe.
- **Proper error responses**: Catch blocks that return 401, 403, or call
  `next(err)` / re-raise the exception are safe. The exception path
  denies access.
- **Framework-level exception handling**: Framework-provided global
  exception filters or error handlers that automatically map security
  exceptions to 401/403 responses are safe if they are configured
  correctly.
- **Graceful degradation of optional features**: Try/catch around
  feature flags, caching, or prefetch operations where the fallback is
  safe and does not bypass security. Permission checks must not be in
  the fallback path.
- **Rate limiter connection failure fallthrough**: A rate limiter backed
  by Redis/external service may intentionally allow requests through on
  connection failure to maintain availability. This requires explicit
  design documentation; if present, it is a deliberate tradeoff and not
  a defect.

## References

- `references/python.md`: Python patterns for Django, Flask, FastAPI,
  generic decorators, and assertions.
- `references/php.md`: PHP patterns for Laravel, Symfony, generic
  middleware, and assertions.
- `references/javascript.md`: Node patterns for Express, Koa, and
  Fastify.
- `references/typescript.md`: TypeScript patterns for NestJS, typed
  Express middleware, and Fastify.
