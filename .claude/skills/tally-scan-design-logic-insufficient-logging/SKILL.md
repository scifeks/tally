---
name: tally-scan-design-logic-insufficient-logging
description: >
  Scan the target repo for insufficient logging of security events.
  Detects authentication failures, permission changes, admin actions,
  and exception handlers that silently swallow security errors without
  audit trails, making incident investigation and attack detection
  impossible. Emits findings shaped for Tally MCP submission (rule_id
  `design_logic.insufficient_logging`, CWE-778, severity medium).
  Invoke when the user says "insufficient logging", "missing audit
  trails", "security event logging", or when dispatched by
  `tally-scan-external`.
---

# Tally scanner: Insufficient logging of security events

Detects security-relevant operations that lack logging, making it
impossible to detect attacks or investigate incidents. Runs per-file
in the target repo (as dispatched by the `tally-scan-external`
orchestrator, or standalone when the user invokes this skill directly).
Emits a JSON list of findings; the orchestrator or the user submits
them to Tally through the `submit_finding` MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `design_logic.insufficient_logging` |
| Primary CWE | `CWE-778` |
| OWASP 2025 category | `Security Logging and Monitoring Failures` |
| Default severity | `medium` |
| Parent label (dedup) | `InsufficientLogging` |

Source: `docs/roadmap/TAL-148/taxonomy.md` T3 row.

## Detection matrix

### Python

- **Login/logout without logging**: An authentication handler (login
  view, middleware, decorator) completes without calling any logging
  function when success or failure occurs. The function returns or
  calls next without logging.
- **Auth failure caught silently**: `except Exception: pass` or
  `except: pass` around an authentication check, with no logging before
  the catch block swallows the error.
- **Permission check without logging**: A permission or authorization
  check (database query, external provider call) completes without
  logging the outcome (allowed or denied).
- **Password reset/change without audit**: A password reset or change
  handler executes without logging the user, timestamp, or outcome.
- **Admin action without logging**: Operations like user creation, role
  assignment, or group membership changes complete without audit
  logging.
- **Exception silently caught in security context**: `try: security_op()
  except: pass` where the operation is auth, permission, rate limit,
  or signature-related and no logging occurs.

Defer to `references/python.md` for vulnerable-vs-safe snippets.

### PHP

- **Login controller without logging**: A login action handler returns
  success or failure without logging the attempt (user, timestamp,
  success/failure).
- **Auth check without logging on failure**: An authorization check
  throws or returns false without logging the denial.
- **Empty catch wrapping security operation**: `catch (Exception $e)
  { }` silently swallowing a security operation (auth, permission,
  signature verification) with no logging.
- **Admin panel action without audit**: User management endpoints
  (create, delete, role change) execute without logging who performed
  the action and what changed.
- **Middleware catching auth exception silently**: `catch
  (AuthException $e) { return $next($request); }` without logging the
  auth failure before proceeding.

Defer to `references/php.md` for vulnerable-vs-safe snippets.

### JavaScript

- **Express auth middleware without logging**: An auth middleware
  completes successfully or fails without calling a logger (console.log,
  winston, pino, etc.). The middleware returns or calls next without
  logging the outcome.
- **Promise rejection silently caught**: A promise-based auth check with
  `.catch()` handler that does not log before calling next() or
  returning success.
- **Unhandled promise rejection in auth**: A promise-based auth
  operation without a `.catch()` handler, so failures go unlogged.
- **Admin API endpoint without action logging**: Routes handling admin
  operations (user creation, deletion, permission changes) complete
  without logging who invoked the endpoint and what action occurred.
- **Rate limit failure not logged**: A rate limiter that silently
  fails-open (allows requests through) when Redis/backend is
  unavailable, with no logging of the degraded state.

Defer to `references/javascript.md` for vulnerable-vs-safe snippets.

### TypeScript

- **NestJS guard without logging**: A `canActivate()` guard method
  returns false or throws without logging the denial, the user
  identity, or the resource being protected.
- **Async auth middleware without logging**: An async auth function
  that catches a promise rejection but does not log before returning
  success or calling next.
- **Exception filter swallowing security exception without logging**: A
  global exception filter catches auth or permission exceptions without
  logging them before returning a response.
- **Decorator wrapping permission check without logging**: A decorator
  that verifies permissions or roles without logging the outcome
  (allowed or denied).
- **Fastify hook without logging**: An `onRequest` or `onPreHandler`
  hook performs auth validation but does not log failures or successes.

Defer to `references/typescript.md` for vulnerable-vs-safe snippets.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the security operation or
  handler.
- `meta.code_snippet`: 2-6 lines of source showing the operation and
  the absence of logging.
- `meta.reasoning`: one sentence explaining why the lack of logging
  makes incident detection or investigation impossible.
- When traceable: `meta.taint_source` naming the security operation
  (login, permission check, password reset, admin action).

Set `confidence`:

- `confirmed` when a security operation is explicit and no logging
  function call appears in the handler path.
- `probable` when logging is plausible but not visible (exception is
  swallowed silently).
- `potential` when the operation is security-adjacent but logging is
  not strictly required (e.g., feature flags).

## Output payload skeleton

Emit one JSON object per finding with these fixed fields for
`design_logic.insufficient_logging`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing the security operation, the lack
  of logging, and how this impairs incident response>",
  "severity": "medium",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-778"],
  "finding_type": ["vulnerability"],
  "rule_id": "design_logic.insufficient_logging",
  "meta": {
    "title": "<short human title, e.g. 'Login handler does not log
    authentication attempts'>",
    "owasp_name": "Security Logging and Monitoring Failures",
    "remediation": "<per-finding, per D19; see remediation guidance
    below>",
    "code_snippet": "<2-6 lines of source showing the operation and
    absence of logging>",
    "reasoning": "<one sentence explaining why the lack of logging is
    a defect>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for the
full field list and validator behavior.

## Remediation guidance for the scanner

Per D19, write `meta.remediation` inline based on the actual framework
observed in the code. Examples of good remediation strings:

- **Python Django auth middleware**: `Log all authentication attempts
  (success and failure) with the username, timestamp, and result.
  Use logger.info() for success and logger.warning() for failure.
  Include the client IP address if available.`
- **Python FastAPI login endpoint**: `Add logging at the start and end
  of the login handler. Log the username and outcome (success or
  specific failure reason). Use a structured logger that includes
  timestamp and client IP.`
- **PHP Laravel middleware**: `Log authentication failures in the catch
  block. Use Log::warning('User login failed', ['user' =>
  $username, 'ip' => $request->ip()]). Also log successful logins at
  Log::info() level.`
- **JavaScript Express auth middleware**: `Add logging via winston or
  pino. Log successful auth and all failures. Include the request path,
  HTTP method, client IP, and reason for denial in each log line.`
- **TypeScript NestJS guard**: `Inject the Logger service and log in
  canActivate(). Log both grants and denials with the resource being
  protected, the user identity, and the outcome.`
- **Admin action logging**: `Log all state-changing admin operations
  (user creation, deletion, role changes). Include who performed the
  action (user ID), when (timestamp), what changed (old and new values),
  and the client IP.`
- **Exception in security context**: `When catching an exception in an
  auth handler, log the exception before proceeding. Include the stack
  trace, the operation that failed, and any identifiable context (user
  ID, request path).`

Keep it two to four sentences. Vague guidance ("add logging") is worse
than no guidance.

## Common false positives

- **Health check endpoints**: Endpoints like `/health`, `/ping`, or
  `/status` that return status without authentication. Logging all
  requests to health endpoints produces noise; skip them.
- **Static file serving**: Routes serving CSS, JavaScript, images, or
  static HTML. Logging every static file request creates excessive log
  volume.
- **Public read-only endpoints**: Unauthenticated endpoints that serve
  public data (public API docs, product info, blog posts). Logging
  every read to public data produces noise.
- **Test code and fixtures**: Login handlers, auth middleware, or
  permission checks in test files, fixtures, or factory code.
- **Centralized logging middleware**: A route logs successfully through
  a framework-level logging middleware or decorator that runs after the
  handler. If detected, the operation IS logged.
- **Feature flag or analytics**: Try/catch around feature detection or
  analytics calls where failure is acceptable and does not grant access.
- **Caching or prefetch failures**: Exception handling for cache misses
  or prefetch operations where the fallback is safe and does not bypass
  security.
- **Optional components**: Try/catch around optional integrations
  (Slack notifications, email delivery) where the main operation
  succeeds even if the optional step fails.

## References

- `references/python.md`: Python patterns for Django, Flask, FastAPI,
  and generic handlers.
- `references/php.md`: PHP patterns for Laravel, Symfony, and generic
  middleware.
- `references/javascript.md`: Node patterns for Express, Koa, and
  Fastify.
- `references/typescript.md`: TypeScript patterns for NestJS, typed
  Express middleware, and Fastify.
