---
name: tally-scan-authentication-weak-or-missing-authn
description: >
  Scan the target repo for weak or missing authentication defects.
  Detects endpoints and route handlers without authentication
  guards, hardcoded credentials in authentication logic, and
  authentication bypass conditions. Emits findings shaped for
  Tally MCP submission (rule_id
  `authentication.weak_or_missing_authn`, CWE-287, severity high).
  Invoke when the user says "missing authentication", "weak auth",
  "unauthenticated endpoint", "auth bypass", or when dispatched
  by `tally-scan-external`.
---

# Tally scanner: Weak or missing authentication

Detects route handlers and endpoints that accept requests without
verifying caller identity, and authentication implementations that
use hardcoded or bypassable credentials. Runs per-file in the
target repo (as dispatched by the `tally-scan-external`
orchestrator, or standalone when the user invokes this skill
directly). Emits a JSON list of findings; the orchestrator or the
user submits them to Tally through the `submit_finding` MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `authentication.weak_or_missing_authn` |
| Primary CWE | `CWE-287` |
| Secondary CWE | `CWE-306` |
| OWASP 2025 category | `Authentication Failures` |
| Default severity | `high` |
| Parent label (dedup) | `WeakAuthN` |


## Detection matrix

### Python

- **Flask route without auth**: a route handler decorated with
  `@app.route` or `@blueprint.route` that handles sensitive
  operations (user data, admin actions, file access) without
  `@login_required` from `flask-login` or a custom authentication
  decorator.
- **Django view without auth**: a function view without
  `@login_required` or a class-based view without
  `LoginRequiredMixin` that serves protected resources. Check
  `urls.py` for routes that map to unprotected views.
- **FastAPI endpoint without auth dependency**: a route function
  without `Depends(get_current_user)` or an equivalent
  authentication dependency in its signature.
- **Django REST framework view without auth**: a view or viewset
  without `authentication_classes` or `permission_classes` set,
  and no global default in `REST_FRAMEWORK` settings.
- **Hardcoded credentials**: `if password == "admin123"` or
  `token = "hardcoded_secret"` in authentication logic.

Read `references/python.md` for vulnerable-vs-safe code patterns.

### PHP

- **Laravel route without middleware**: a route definition in
  `routes/web.php` or `routes/api.php` serving protected
  resources without the `auth` middleware applied via
  `->middleware('auth')` or a route group.
- **Laravel controller without middleware**: a controller
  constructor without `$this->middleware('auth')` where
  methods handle sensitive operations.
- **Symfony controller without security**: a controller action
  without `#[IsGranted]` attribute, `@Security` annotation, or
  `access_control` rules in `security.yaml` covering the route.
- **Hardcoded credentials**: `if ($password === 'admin')` or
  API keys defined as string literals in authentication code.

Read `references/php.md` for vulnerable-vs-safe code patterns.

### JavaScript

- **Express route without auth middleware**: a route handler
  registered with `app.get()`, `app.post()`, etc. serving
  protected resources without an authentication middleware in
  the handler chain.
- **Missing Passport.js guard**: a route that should require
  authentication but lacks `passport.authenticate('jwt')` or
  `passport.authenticate('session')` in the middleware chain.
- **Hardcoded credentials**: `if (req.body.password === 'secret')`
  or API keys as string literals in route handlers.
- **Missing Authorization header check**: an API endpoint that
  does not verify the `Authorization` header before processing
  the request.

Read `references/javascript.md` for vulnerable-vs-safe code
snippets.

### TypeScript

- **NestJS controller without guard**: a controller or method
  without `@UseGuards(AuthGuard)` or a custom authentication
  guard, where the endpoint handles protected resources.
- **NestJS missing global guard**: when `APP_GUARD` is not
  registered globally and individual controllers lack explicit
  guards.
- **GraphQL resolver without auth**: a NestJS GraphQL resolver
  method without an authentication guard applied.

Read `references/typescript.md` for vulnerable-vs-safe code
snippets.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the unprotected route
  handler or the weak authentication logic.
- `meta.code_snippet`: 2-6 lines of source containing the
  handler or authentication check.
- `meta.reasoning`: one sentence explaining why this endpoint
  or authentication check is a defect.
- When the route definition is in a separate file:
  `meta.taint_source` naming the route path (e.g.
  "/api/users/:id").

Set `confidence`:

- `confirmed` when the route handler clearly processes sensitive
  data and no authentication guard exists in the middleware chain
  or decorator list.
- `probable` when the handler name or path suggests sensitivity
  (e.g. `/admin/`, `/api/users/`) but the data sensitivity is
  not directly visible.
- `potential` when the endpoint is public-facing but the
  sensitivity of the data is ambiguous.

## Output payload skeleton

Emit one JSON object per finding with these fixed fields for
`authentication.weak_or_missing_authn`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing the missing auth>",
  "severity": "high",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-287", "CWE-306"],
  "finding_type": ["vulnerability"],
  "rule_id": "authentication.weak_or_missing_authn",
  "meta": {
    "title": "<short title, e.g. 'Missing auth on user data endpoint'>",
    "owasp_name": "Authentication Failures",
    "remediation": "<per-finding>",
    "code_snippet": "<2-6 lines of source>",
    "taint_source": "<route path, when identifiable>",
    "reasoning": "<one sentence explaining the defect>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for
the full field list and validator behavior.

## Remediation guidance for the scanner

Write `meta.remediation` inline based on the actual
framework observed in the code. Examples of good remediation
strings:

- **Flask missing decorator**: `Add @login_required from
  flask-login to this route handler. If the route should
  allow both authenticated and anonymous access, check
  current_user.is_authenticated inside the handler instead.`
- **Django missing decorator**: `Add @login_required to this
  view function, or add LoginRequiredMixin to the class-based
  view's base classes. For API views, set
  permission_classes = [IsAuthenticated] on the view class.`
- **FastAPI missing dependency**: `Add a Depends(get_current_user)
  parameter to this endpoint function. Define get_current_user
  as an async dependency that validates the bearer token and
  raises HTTPException(401) on failure.`
- **Laravel missing middleware**: `Add ->middleware('auth') to
  this route definition, or apply it to the route group. For
  API routes, use ->middleware('auth:sanctum') or the
  appropriate guard.`
- **NestJS missing guard**: `Add @UseGuards(AuthGuard) to this
  controller or method. For global protection, register
  AuthGuard as APP_GUARD in the application module and use
  @Public() to exempt specific routes.`
- **Hardcoded credentials**: `Remove the hardcoded credential
  and load it from an environment variable or a secrets
  manager. Hash passwords with bcrypt or argon2 before
  comparison; never compare plaintext.`

Keep it two to four sentences.

## Common false positives

- **Intentionally public endpoints**: login pages, registration
  forms, password reset flows, health checks, and public API
  documentation are expected to be unauthenticated. Do not flag
  them.
- **Global middleware**: if authentication middleware is applied
  globally (via `APP_GUARD` in NestJS, `@login_required` on a
  base class, or a route group in Laravel), individual routes
  within the scope are protected even without per-route
  decorators. Verify the middleware stack before flagging.
- **Webhook endpoints**: inbound webhook routes often validate
  via HMAC signature rather than bearer tokens. If the handler
  validates the webhook signature, it is authenticated.
- **Static file routes**: routes serving CSS, JS, images, or
  other static assets are not authentication targets.

## References

- `references/python.md`: Flask, Django, FastAPI, DRF patterns.
- `references/php.md`: Laravel and Symfony patterns.
- `references/javascript.md`: Express and Passport.js patterns.
- `references/typescript.md`: NestJS guard and global auth
  patterns.
