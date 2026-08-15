---
name: tally-scan-access-control-idor-bola
description: >
  Scan the target repo for insecure direct object reference and broken
  object-level authorization defects. Detects request handlers that use
  user-supplied identifiers to fetch resources without ownership or
  authorization checks. Emits findings shaped for Tally MCP submission
  (rule_id `access_control.idor_bola`, CWE-639, severity high). Invoke
  when the user says "IDOR", "BOLA", "insecure direct object reference",
  "check for IDOR", or when dispatched by `tally-scan-external`.
---

# Tally scanner: Insecure Direct Object Reference (IDOR) / Broken
# Object-Level Authorization (BOLA)

Detects sinks where user-controlled identifiers are used to fetch
resources from a database or object store without verifying the requester
owns or has authorization to access the resource. Runs per-file in the
target repo (as dispatched by the `tally-scan-external` orchestrator, or
standalone when the user invokes this skill directly). Emits a JSON list
of findings; the orchestrator or the user submits them to Tally through
the `submit_finding` MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `access_control.idor_bola` |
| Primary CWE | `CWE-639` |
| Secondary CWE | `CWE-284` |
| OWASP 2025 category | `Broken Access Control` |
| Default severity | `high` |
| Parent label (dedup) | `AuthzBypass` |

Source: `docs/roadmap/TAL-148/taxonomy.md` T3 row 15.

## Detection matrix

### Python

- **Django ORM direct fetch**: `Model.objects.get(pk=request_id)` or
  `Model.objects.get(id=request.GET['id'])` without filtering by
  `request.user`.
- **Django REST Framework viewset**: overriding `get_queryset()` or
  `get_object()` without scoping to `self.request.user`.
- **FastAPI path parameter**: handlers using `@app.get('/{resource_id}')
  ` that fetch from a DB with the path parameter directly without
  checking authorization.
- **SQLAlchemy direct query**: `session.query(Model).get(request_id)`
  without a WHERE clause filtering by the authenticated user or
  ownership field.
- **get_object_or_404**: Django's shortcut used without a queryset that
  scopes to the current user.

Defer to `references/python.md` for vulnerable-vs-safe snippets.

### PHP

- **Laravel model find**: `Model::find($request->id)` without checking if
  the authenticated user owns the resource.
- **Laravel query builder**: `Model::where('id', $request->input('id'))
  ->first()` without filtering by `Auth::id()`.
- **Route model binding**: Laravel's implicit binding without
  `ScopedBindings` middleware or explicit policy check.
- **Direct database access**: raw queries using `$_GET['id']` or
  `request()->input('id')` without user-scoped WHERE clauses.

Defer to `references/php.md` for vulnerable-vs-safe snippets.

### JavaScript

- **Mongoose findById**: `Model.findById(req.params.id)` without
  checking that `req.user` owns the resource.
- **Sequelize findOne**: `Model.findOne({where: {id: req.params.id}})`
  without a filter for the authenticated user.
- **Knex query**: `.where({id: req.params.id})` without scoping to
  `req.user.id` or a tenant/owner field.
- **MongoDB direct find**: `collection.findOne({_id: ObjectId(req.params
  .id)})` without tenant or ownership filtering.

Defer to `references/javascript.md` for vulnerable-vs-safe snippets.

### TypeScript

- **Prisma findUnique**: `prisma.resource.findUnique({where: {id:
  req.params.id}})` without a subsequent ownership check or a
  tenant-scoped filter.
- **TypeORM findOneBy**: `repository.findOneBy({id})` without scoping
  the query to the authenticated user.
- **NestJS handler**: request handlers using `@Param('id')` without a
  guard or interceptor that verifies the authenticated user has
  permission to access the resource.
- **Same JavaScript sinks apply**: Sequelize, Knex, and MongoDB patterns
  work in TypeScript projects as well.

Defer to `references/typescript.md` for vulnerable-vs-safe snippets.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the sink call (the resource fetch).
- `meta.code_snippet`: 2-6 lines of source containing the sink.
- `meta.reasoning`: one sentence explaining why the pattern is an IDOR
  at this location.
- When the authorization context is in the same file: `meta.taint_source`
  naming the request parameter or upstream variable that reaches the sink
  without authorization.

Set `confidence`:

- `confirmed` when an unfiltered fetch is traced from a request handler
  to the sink in the same file and no authorization check is visible in
  the call path.
- `probable` when the sink pattern matches (direct fetch without user
  filter visible), but the authorization boundary is not fully traced.
- `potential` when the fetch pattern is suspicious but it is unclear
  whether the resource is user-controlled.

## Output payload skeleton

Emit one JSON object per finding with these fixed fields for
`access_control.idor_bola`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing the sink, the source, and what an
    attacker can do>",
  "severity": "high",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-639", "CWE-284"],
  "finding_type": ["vulnerability"],
  "rule_id": "access_control.idor_bola",
  "meta": {
    "title": "<short human title, e.g. 'IDOR via unfiltered ORM query
      in user profile handler'>",
    "owasp_name": "Broken Access Control",
    "remediation": "<per-finding, per D19; see remediation guidance
      below>",
    "code_snippet": "<2-6 lines of source containing the sink>",
    "taint_source": "<request parameter or upstream variable, when
      traceable>",
    "reasoning": "<one sentence explaining the defect at this location>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for the
full field list and validator behavior.

## Remediation guidance for the scanner

Per D19, write `meta.remediation` inline based on the actual library
observed in the code. Examples of good remediation strings:

- **Django ORM**: `Filter the queryset to the authenticated user:
  Model.objects.filter(owner=self.request.user).get(pk=pk). For DRF
  viewsets, override get_queryset() to return self.get_queryset()
  .filter(owner=self.request.user).`
- **Laravel Eloquent**: `Scope the query to the authenticated user:
  Model::where('id', $id)->where('user_id', Auth::id())->first(). Or
  use a policy: $this->authorize('view', $model);.`
- **FastAPI**: `Create a dependency that fetches the resource and
  verifies ownership: def get_user_resource(resource_id: int, current_user:
  User = Depends(get_current_user)) -> Resource: resource = db.query(
  Resource).get(resource_id); if resource.owner_id != current_user.id:
  raise HTTPException(403); return resource.`
- **Sequelize / Mongoose**: `Add a where clause filtering by the
  authenticated user: Model.findOne({where: {id: req.params.id,
  user_id: req.user.id}}) (Sequelize) or Model.findOne({_id: req.params
  .id, user_id: req.user.id}) (Mongoose).`
- **Prisma**: `Use a where clause scoped to the user: prisma.resource
  .findUnique({where: {id: req.params.id}, AND: [{owner_id:
  req.user.id}]}) or filter after fetch: const resource = await
  prisma.resource.findUnique(...); if (resource.owner_id !==
  req.user.id) throw new Error('Forbidden');.`

Keep it two to four sentences. Vague guidance ("add an authorization
check") is worse than no guidance.

## Common false positives

- **Admin endpoints**: endpoints restricted to admins (verified by a
  middleware or decorator earlier in the request path) may legitimately
  access all resources. Flag only if no authorization guard is visible.
- **Public resources**: endpoints serving public data (blog posts, product
  listings, documentation) with no ownership concept. Do not flag.
- **Fetch-then-authorize**: endpoints that fetch the resource and then
  check authorization in the next statement. Flag if the authorization
  check fails or is missing, not if it is present.
- **Non-user-controlled IDs**: resource IDs derived from the authenticated
  user's session, JWT claims, or other non-request-parameter sources are
  safe by design.
- **Resource IDs that are the authenticated user's own ID**: endpoints
  fetching a resource where the ID is the authenticated user's own ID
  (e.g., GET /api/user/me) are safe even without an explicit ownership
  check.

## References

- `references/python.md`: Python patterns for Django ORM, DRF, FastAPI,
  SQLAlchemy.
- `references/php.md`: PHP patterns for Laravel Eloquent, query builder,
  raw queries.
- `references/javascript.md`: Node patterns for Mongoose, Sequelize, Knex,
  MongoDB.
- `references/typescript.md`: TypeScript patterns for Prisma, TypeORM,
  NestJS.
