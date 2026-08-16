---
name: tally-scan-access-control-csrf
description: >
  Scan the target repo for cross-site request forgery defects. Detects
  state-changing handlers missing CSRF token validation, explicit CSRF
  exemptions on sensitive endpoints, and form submissions without
  anti-CSRF tokens. Emits findings shaped for Tally MCP submission
  (rule_id `access_control.csrf`, CWE-352, severity high). Invoke when
  the user says "CSRF", "cross-site request forgery", "check for CSRF",
  or when dispatched by `tally-scan-external`.
---

# Tally scanner: Cross-site request forgery (CSRF)

Detects state-changing handlers (POST, PUT, DELETE) that accept requests
without validating a CSRF token or that explicitly bypass CSRF protection.
Runs per-file in the target repo (as dispatched by the
`tally-scan-external` orchestrator, or standalone when the user invokes
this skill directly). Emits a JSON list of findings; the orchestrator or
the user submits them to Tally through the `submit_finding` MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `access_control.csrf` |
| Primary CWE | `CWE-352` |
| OWASP 2025 category | `Broken Access Control` |
| Default severity | `high` |
| Parent label (dedup) | `CSRF` |


## Detection matrix

### Python

- **Django view with `@csrf_exempt`**: a view function decorated with
  `@csrf_exempt` on a POST, PUT, or DELETE handler. The safe form relies
  on `CsrfViewMiddleware` (enabled by default) or wraps the handler with
  `ensure_csrf_cookie`.
- **Django CBV with `csrf_exempt()` in URLconf**: a class-based view
  whose `dispatch` is wrapped with `csrf_exempt()` in the route
  configuration. Safe form uses `CsrfViewMiddleware` (default) or
  `@ensure_csrf_cookie` on the view.
- **Flask POST route without CSRFProtect**: a POST/PUT/DELETE route
  handler with no `validate_csrf()` call and Flask-WTF `CSRFProtect`
  not initialized or not applied globally. Safe form initializes
  `CSRFProtect(app)` and includes `{{ csrf_token() }}` in templates.
- **DRF APIView with CSRF check bypassed**: a DRF `SessionAuthentication`
  view with `csrf_exempt` decorator. Safe form removes the exemption
  and relies on DRF's CSRF middleware.
- **FastAPI POST endpoint without token validation**: a POST/PUT/DELETE
  route using cookie-based sessions with no CSRF token validation logic
  in the handler. Safe form implements token validation on request.

Read `references/python.md` for vulnerable-vs-safe code patterns.

### PHP

- **Laravel route in `$except` array**: a route excluded from the
  `VerifyCsrfToken` middleware's `$except` array on a POST/PUT/DELETE
  handler. Safe form removes the route from the array and includes
  `@csrf` directive in Blade forms.
- **Laravel route group missing `web` middleware**: a route group or
  individual route not wrapped in the `web` middleware (which includes
  CSRF verification). Safe form applies the `web` middleware to the
  route group.
- **Symfony form with `csrf_protection` disabled**: a form with
  `csrf_protection: false` option. Safe form omits the option (default
  true) and includes CSRF token in templates.
- **Raw PHP state-changing handler without token validation**: a
  POST/PUT/DELETE handler with no CSRF token generation or validation
  logic. Safe form generates a token on GET, validates it on POST, and
  uses `hash_equals` for comparison.

Read `references/php.md` for vulnerable-vs-safe code patterns.

### JavaScript

- **Express POST/PUT/DELETE without CSRF middleware**: a route handler
  using `app.post`, `app.put`, or `app.delete` with no `csurf` or
  `csrf-csrf` middleware registered. Safe form applies middleware:
  `app.use(csurf({ cookie: true }))` or equivalent.
- **Koa route without CSRF middleware**: a Koa route for state-changing
  methods with no CSRF middleware in the request chain. Safe form uses
  `koa-csrf` or similar middleware.
- **Hapi route without `crumb` plugin**: a Hapi route on a POST/PUT/DELETE
  method with the `crumb` CSRF plugin not registered or the route
  exempted without justification. Safe form registers the plugin
  globally.
- **Cookie-based session endpoints without CSRF token header check**: a
  handler using cookie authentication for state-changing requests with
  no validation of a CSRF token header. Safe form validates a token from
  the request body or header.

Read `references/javascript.md` for vulnerable-vs-safe code patterns.

### TypeScript

- **NestJS controller POST handler without CSRF guard**: a controller
  method decorated with `@Post`, `@Put`, or `@Delete` with no CSRF guard
  or validation pipe. Safe form applies `@UseGuards(CsrfGuard)` or
  equivalent.
- **Fastify POST route without CSRF plugin**: a POST/PUT/DELETE route
  handler registered on a Fastify app where the
  `@fastify/csrf-protection` plugin is not installed or not applied.
  Safe form registers the plugin globally.

Read `references/typescript.md` for vulnerable-vs-safe code patterns.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the handler definition (the route
  decorator or middleware registration point).
- `meta.code_snippet`: 2-6 lines of source containing the handler or
  exemption.
- `meta.reasoning`: one sentence explaining why the handler lacks CSRF
  protection at this location.
- When the exemption is explicit (e.g. `@csrf_exempt`, `$except` array):
  `meta.taint_source` naming the exemption directive or configuration
  field.

Set `confidence`:

- `confirmed` when the exemption is explicit in code (decorator,
  configuration key, middleware exclusion).
- `probable` when a POST/PUT/DELETE handler is found with no CSRF
  validation logic and the framework's default CSRF is not provably
  active.
- `potential` when a handler pattern is suspicious but framework
  configuration is unclear.

## Output payload skeleton

Emit one JSON object per finding with these fixed fields for
`access_control.csrf`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing the handler, its method, and
  the CSRF risk>",
  "severity": "high",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-352"],
  "finding_type": ["vulnerability"],
  "rule_id": "access_control.csrf",
  "meta": {
    "title": "<short human title, e.g. 'POST handler with
    @csrf_exempt'>",
    "owasp_name": "Broken Access Control",
    "remediation": "<per-finding; see remediation
    guidance below>",
    "code_snippet": "<2-6 lines of source containing the handler
    or exemption>",
    "taint_source": "<exemption directive or config field name, if
    explicit>",
    "reasoning": "<one sentence explaining the defect at this
    location>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for
the full field list and validator behavior.

## Remediation guidance for the scanner

Write `meta.remediation` inline based on the actual
framework observed in the code. Examples of good remediation
strings:

- **Django**: `Remove @csrf_exempt from the view. Django's
  CsrfViewMiddleware is enabled by default and validates POST
  requests; the middleware requires a CSRF token in the form or
  X-CSRFToken header.`
- **Flask with CSRFProtect**: `Initialize Flask-WTF's CSRFProtect
  (csrf = CSRFProtect(app)) at app startup, then include
  {{ csrf_token() }} in the form template. The protect decorator
  validates the token on POST.`
- **Express with csurf**: `Register the csurf middleware:
  app.use(csurf({ cookie: true })). In the GET handler, pass
  req.csrfToken() to the template; in the POST handler, validate
  is automatic.`
- **Laravel**: `Remove the route from the VerifyCsrfToken
  middleware's $except array. Ensure the route group includes the
  web middleware, which applies CSRF verification. Include @csrf
  in Blade forms.`
- **Fastify**: `Install and register @fastify/csrf-protection:
  app.register(require('@fastify/csrf-protection')). The plugin
  validates tokens on state-changing requests.`

Keep it two to four sentences. Vague guidance ("add CSRF
protection") is worse than no guidance.

## Common false positives

- **GET/HEAD/OPTIONS handlers**: these HTTP methods are idempotent
  and safe; CSRF only applies to state-changing methods (POST, PUT,
  DELETE, PATCH).
- **API endpoints using token-based auth (JWT, API key)**: endpoints
  with Bearer token authentication or API key headers do not require
  CSRF protection because tokens are not automatically sent by the
  browser.
- **Routes protected by CSRF middleware at app or router level**: a
  POST handler inside a route group or app with global CSRF
  middleware is safe; do not flag it.
- **WebSocket handlers**: WebSocket connections are not vulnerable to
  CSRF in the same way; they use their own upgrade protocol.
- **Endpoints that only read data**: POST handlers that do not mutate
  state (e.g. GraphQL queries, search endpoints) are not CSRF risks,
  though using POST for queries is non-standard.

## References

- `references/python.md`: Python patterns for Django, Flask-WTF, DRF,
  FastAPI.
- `references/php.md`: PHP patterns for Laravel, Symfony, raw PHP.
- `references/javascript.md`: Node patterns for Express, Koa, Hapi.
- `references/typescript.md`: TypeScript patterns for NestJS, Fastify.
