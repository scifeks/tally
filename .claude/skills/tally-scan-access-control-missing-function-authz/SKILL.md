---
name: tally-scan-access-control-missing-function-authz
description: >
  Scan the target repo for missing function-level authorization
  defects. Detects privileged or state-changing endpoints and
  controller actions that lack authorization middleware, decorators,
  or permission checks. Emits findings shaped for Tally MCP
  submission (rule_id `access_control.missing_function_authz`,
  CWE-862, severity high). Invoke when the user says "missing
  authorization", "no auth check", "unprotected endpoint", or when
  dispatched by `tally-scan-external`.
---

# Tally scanner: Missing function-level authorization

Detects endpoints, routes, and controller actions that perform state
changes or access protected resources without explicit authorization
checks or middleware enforcement. Runs per-file in the target repo
(as dispatched by the `tally-scan-external` orchestrator, or
standalone when the user invokes this skill directly). Emits a JSON
list of findings; the orchestrator or the user submits them to Tally
through the `submit_finding` MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `access_control.missing_function_authz` |
| Primary CWE | `CWE-862` |
| Secondary CWE | `CWE-284` |
| OWASP 2025 category | `Broken Access Control` |
| Default severity | `high` |
| Parent label (dedup) | `AuthzBypass` |


## Detection matrix

### Python

- **Django view without auth**: POST, PUT, DELETE handler on a view
  class or function lacking `@login_required` or
  `@permission_required('app.action')` decorator.
- **DRF view with AllowAny**: class-based view with
  `permission_classes = []` or `AllowAny()` on create, update, or
  destroy actions.
- **DRF viewset without permission class**: any view with no
  `permission_classes` attribute on a state-changing action (create,
  update, partial_update, destroy).
- **FastAPI endpoint without Depends**: POST, PUT, DELETE endpoint
  lacking `Depends(get_current_user)` or a security scheme
  definition.
- **Flask route without @login_required**: state-changing route
  registered without `@login_required` decorator from Flask-Login.

Read `references/python.md` for vulnerable-vs-safe code patterns.

### PHP

- **Laravel controller method not protected**: controller action
  invoked on a route without `auth` or `can` middleware applied.
- **Laravel route without middleware**: route registered with
  `Route::post()`, `::put()`, `::delete()` without `->middleware('
  auth')` or `->middleware('can:action')` chained.
- **Symfony controller without #[IsGranted]**: controller action
  lacking `#[IsGranted(...)]` attribute on state-changing methods.
- **Raw PHP endpoint without session check**: server-side script
  lacking `session_start()` and a conditional auth check before
  processing state changes.

Read `references/php.md` for vulnerable-vs-safe code patterns.

### JavaScript

- **Express route without middleware**: POST, PUT, DELETE route
  without an `authMiddleware` or equivalent auth function in the
  handler chain.
- **Express router without auth group**: router or router group
  missing `authMiddleware` on admin or protected paths.
- **Koa route without auth middleware**: handler registered without
  a preceding auth middleware in the middleware chain.

Read `references/javascript.md` for vulnerable-vs-safe code patterns.

### TypeScript

- **NestJS controller without @UseGuards**: controller method lacking
  `@UseGuards(AuthGuard)` or equivalent guard on privileged
  handlers.
- **NestJS handler missing @Roles decorator**: POST, PUT, DELETE
  method without `@Roles('admin')` or `@Roles('user')` when
  role-restricted operations are intended.
- **Fastify route without preHandler**: handler registered without
  an auth `preHandler` hook or security scheme.

Read `references/typescript.md` for vulnerable-vs-safe code patterns.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the unprotected endpoint or
  handler declaration.
- `meta.code_snippet`: 2-6 lines of source containing the handler or
  route definition.
- `meta.reasoning`: one sentence explaining why the endpoint lacks
  authorization and what data or action it exposes.
- When the operation is clearly state-changing or privileged:
  `meta.attack_vector` naming how an attacker would trigger the
  unprotected handler.

Set `confidence`:

- `confirmed` when the endpoint is a POST, PUT, or DELETE with no
  visible auth decorator, middleware, or permission check.
- `probable` when the route is registered for a handler but the
  handler auth status is not visible in the same file.
- `potential` when the handler is conditional or the intent is
  inferred from naming.

## Output payload skeleton

Emit one JSON object per finding with these fixed fields for
`access_control.missing_function_authz`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing the unprotected endpoint, what \
data or action it exposes, and how an attacker would exploit it>",
  "severity": "high",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-862", "CWE-284"],
  "finding_type": ["vulnerability"],
  "rule_id": "access_control.missing_function_authz",
  "meta": {
    "title": "<short human title, e.g. 'Unprotected endpoint \
allows user data update'>",
    "owasp_name": "Broken Access Control",
    "remediation": "<per-finding; see remediation \
guidance below>",
    "code_snippet": "<2-6 lines of source containing the endpoint \
definition>",
    "attack_vector": "<how an attacker would access the \
unprotected endpoint, if applicable>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for
the full field list and validator behavior.

## Remediation guidance for the scanner

Write `meta.remediation` inline based on the actual
framework observed in the code. Examples of good remediation
strings:

- **Django**: `Add @login_required to the view, or wrap the view
  class with LoginRequiredMixin. For permission-specific actions,
  use @permission_required('app.action_name'). Verify the decorated
  method only handles the intended HTTP verbs.`
- **DRF**: `Set permission_classes = [IsAuthenticated] on the
  viewset or view class. For role-restricted operations, create a
  custom Permission class checking user.is_staff or user.groups.`
- **FastAPI**: `Add Depends(get_current_user) to the route handler
  signature. Define a get_current_user function that validates the
  auth token and raises HTTPException(status_code=403) if not
  authenticated.`
- **Flask-Login**: `Decorate the route handler with
  @login_required. For role-based access, create a custom decorator
  wrapping @login_required and checking user.role.`
- **Laravel**: `Apply ->middleware('auth') to the route or route
  group. For role-specific logic, chain ->middleware('can:action').
  Define the Gate or Policy in the AuthServiceProvider.`
- **Symfony**: `Add #[IsGranted('ROLE_ADMIN')] (or the intended role)
  above the controller method. Test with an unauthenticated
  request.`
- **Express**: `Define an authMiddleware function that verifies the
  request token and attaches user info to req.user. Chain it before
  the handler in the route.`
- **NestJS**: `Apply @UseGuards(AuthGuard('jwt')) (or your auth
  strategy) to the method or controller class. For role-based
  access, combine with @Roles('admin') and RolesGuard.`

Keep it two to four sentences. Name the specific decorator,
middleware, or configuration key.

## Common false positives

- **Public endpoints**: login, registration, password reset, health
  checks, OpenAPI documentation routes, webhook endpoints with
  signature verification. These should not be flagged.
- **Auth middleware at router or app level**: routes protected by a
  global middleware applied at the router or app level are safe even
  if the handler has no explicit decorator. Flag only when the
  handler is isolated or the framework requires per-handler checks.
- **Static file and asset handlers**: routes serving CSS, images, or
  JavaScript bundles.
- **OPTIONS and HEAD methods**: preflight and metadata requests
  typically do not require auth.
- **Routes with path-based authentication**: URL segments like
  `/admin/...` that rely on naming convention rather than explicit
  checks are weak but not the same as unprotected; flag only when
  the endpoint path suggests no protection.

## References

- `references/python.md`: Python patterns for Django, DRF, FastAPI,
  Flask-Login.
- `references/php.md`: PHP patterns for Laravel, Symfony.
- `references/javascript.md`: Node patterns for Express, Koa.
- `references/typescript.md`: TypeScript patterns for NestJS,
  Fastify.
