---
name: tally-scan-design-logic-order-of-operations
description: >
  Scan the target repo for order-of-operations bypass defects.
  Detects security controls applied in wrong sequence, authentication
  checks after authorization, validation after persistence, sanitization
  after output rendering, and expensive operations before rate limiting.
  Emits findings shaped for Tally MCP submission (rule_id
  `design_logic.order_of_operations`, CWE-696, severity high). Invoke
  when the user says "order of operations", "wrong middleware order",
  "security control ordering", "authorization before authentication",
  or when dispatched by `tally-scan-external`.
---

# Tally scanner: Order-of-operations bypass

Detects security controls applied in incorrect sequence, allowing an
attacker to bypass defenses by exploiting the ordering weakness. Runs
per-file in the target repo (as dispatched by the `tally-scan-external`
orchestrator, or standalone when the user invokes this skill directly).
Emits a JSON list of findings; the orchestrator or the user submits them
to Tally through the `submit_finding` MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `design_logic.order_of_operations` |
| Primary CWE | `CWE-696` |
| Secondary CWE | `CWE-841` |
| OWASP 2025 category | `Insecure Design` |
| Default severity | `high` |
| Parent label (dedup) | `OrderOfOperations` |

Source: `docs/roadmap/TAL-148/taxonomy.md` T3 row (design logic family).

## Detection matrix

### Python

- **Decorator ordering in Django/Flask views**: an authorization
  decorator (`@login_required`, `@permission_required`) placed above
  an authentication decorator, or vice versa. Django decorators
  execute bottom-up; a guard placed above its upstream dependency
  runs too early.
- **Validation after persistence**: `session.add(model)` or
  `model.save()` called before `validate(data)` completes. Invalid
  data reaches the database.
- **Output after sanitization**: `logger.info(user_data)` or
  `print(user_data)` before `sanitize(data)` or `escape(data)` is
  called. Sensitive data logged unsanitized.
- **File write before path check**: `open(path, 'w').write(content)`
  before a path traversal validation. Arbitrary file writes possible.
- **Rate limit applied after expensive operation**: expensive
  computation (parsing, cryptographic operation, ML inference)
  completed before rate-limit check runs.

Defer to `references/python.md` for vulnerable-vs-safe snippets.

### PHP

- **Middleware registration order**: authorization middleware
  registered before authentication middleware in route group or in
  middleware stack. Unauthed requests reach authz check.
- **Data save before validation**: `$model->save()` called before
  `$validator->validate($data)`. Invalid data persisted to database.
- **Output before encoding**: `echo $input` or `json_encode($data)`
  before `htmlspecialchars()` or output encoding applied. XSS
  possible.
- **File operation before validation**: `file_put_contents($path,
  $content)` before `validate_path($path)` or path traversal check.
  Arbitrary file writes.

Defer to `references/php.md` for vulnerable-vs-safe snippets.

### JavaScript

- **Express middleware order**: authz middleware runs before authn
  middleware in the middleware chain. Express processes middleware
  in registration order (left to right). Unauthed requests reach
  `app.use(checkPermission, authenticate)`.
- **Database write before validation**: `db.save(data)` called before
  Joi/Zod schema validation completes. Invalid data persisted.
- **Response sent before authz check**: async middleware where
  `res.json(data)` is awaited before `if (!isAuthorized())` check
  runs. Race condition allows unauthorized data leak.
- **Sanitization after render**: `DOMPurify.sanitize(html)` called
  after `innerHTML = html` assignment. XSS executes before
  sanitization.

Defer to `references/javascript.md` for vulnerable-vs-safe snippets.

### TypeScript

- **NestJS guard order**: `@UseGuards(AuthzGuard, AuthnGuard)` with
  guards in wrong sequence. NestJS executes guards left-to-right;
  authorization runs before authentication completes. Unauthed user
  reaches authz check.
- **Pipe validation after controller method**: controller method body
  accesses `req.body` fields before the `ValidationPipe` completes.
  Unvalidated data used.
- **Type narrowing after use**: Zod or class-validator parse applied
  after unvalidated data already passed to a service. Type narrowing
  too late.
- **ORM persistence before type check**: Prisma or TypeORM
  `.create()` or `.save()` called before Zod schema validation.

Defer to `references/typescript.md` for vulnerable-vs-safe snippets.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the first control that runs
  out of order.
- `meta.code_snippet`: 2-6 lines of source showing both the
  misordered controls and their relative positions.
- `meta.reasoning`: one sentence explaining why the sequence is a
  defect (e.g., "Authorization runs before authentication completes,
  allowing unauthed users to reach the permission check").
- `meta.control_sequence`: a prose description of the intended vs
  observed ordering.

Set `confidence`:

- `confirmed` when the code clearly shows the misorder and the
  framework's documented execution order confirms the defect.
- `probable` when the misorder is evident and the framework's
  execution order is consistent with the pattern (e.g., middleware
  registration order in Express).
- `potential` when the code suggests an order issue but the control
  flow is complex or the execution order depends on external
  configuration.

## Output payload skeleton

Emit one JSON object per finding with these fixed fields for
`design_logic.order_of_operations`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing which controls are out of order
    and what bypass becomes possible>",
  "severity": "high",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-696", "CWE-841"],
  "finding_type": ["vulnerability"],
  "rule_id": "design_logic.order_of_operations",
  "meta": {
    "title": "<short human title, e.g. 'Authorization before
      authentication in Django view'>",
    "owasp_name": "Insecure Design",
    "remediation": "<per-finding, specific to framework observed;
      see remediation guidance below>",
    "code_snippet": "<2-6 lines of source showing both controls and
      their order>",
    "control_sequence": "<description of the order defect>",
    "reasoning": "<one sentence explaining why this order is insecure>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for the
full field list and validator behavior.

## Remediation guidance for the scanner

Per D19, write `meta.remediation` inline based on the actual library
and framework observed in the code. Examples of good remediation
strings:

- **Django decorator ordering**: `Reorder the decorators so
  authentication runs first. Django decorators execute bottom-up, so
  place @login_required below @require_permission. The authentication
  guard must complete before the authorization check runs.`
- **Django before_request hooks**: `Register the authentication
  handler before the authorization handler in your before_request
  stack. Use app.before_request() in order: first authenticate, then
  authorize.`
- **FastAPI dependency ordering**: `Declare authentication as a
  dependency of the authorization dependency. FastAPI resolves
  dependencies in order; the authn dependency must complete before
  the authz dependency receives its value.`
- **Express middleware chain**: `Reorder the middleware chain:
  app.use(authenticate, authorize, validateRequest, handler). Express
  executes middleware left-to-right. Authentication must precede
  authorization.`
- **NestJS guards**: `Reorder @UseGuards(AuthnGuard, AuthzGuard).
  NestJS executes guards left-to-right; authentication must run before
  authorization.`
- **Validation before persist**: `Call validator before the database
  write. Move schema.validate(data) above db.save(model). Never
  persist unvalidated data.`
- **Sanitization before output**: `Sanitize the value before
  rendering or logging. Move the sanitization call above the template
  or logger call.`
- **Rate limit before expensive operation**: `Apply rate limiting
  before the expensive computation. Move the rate-limit check to the
  beginning of the request handler, before parsing, validation, or
  business logic.`

Keep it two to four sentences. Vague guidance ("fix the order") is
worse than no guidance.

## Common false positives

- **Independent middleware**: middleware or controls that do not depend
  on each other can run in any order. Example: CORS headers and CSP
  headers are independent; either order is safe. Do not flag.
- **Validation at ORM layer**: ORM `before_save` or `saving` hooks run
  validation automatically. This is designed ordering, not a defect.
  Do not flag if the hook fires before the write.
- **Upstream service authentication**: auth handled by a separate
  gateway, sidecar, or upstream proxy that runs before the handler.
  The handler may perform authorization only. Do not flag if
  authentication is proven to complete upstream.
- **Configuration-driven order**: security controls whose order is
  configurable and both orders are documented as valid paths.
- **Already-sanitized data**: logging or rendering data that was
  already sanitized upstream. Do not flag if the value provably
  reaches the sink already clean.

## References

- `references/python.md`: Python patterns for Django, Flask, FastAPI.
- `references/php.md`: PHP patterns for Laravel, Symfony, generic
  middleware.
- `references/javascript.md`: Node patterns for Express, Koa, Fastify.
- `references/typescript.md`: TypeScript patterns for NestJS, Express
  typed middleware, Fastify.
