---
name: tally-scan-access-control-mass-assignment
description: >
  Scan the target repo for mass assignment vulnerabilities (CWE-915).
  Detects ORM create/update calls accepting unfiltered user input,
  serializers without field restrictions, and models lacking property
  access guards. Emits findings shaped for Tally MCP submission
  (rule_id `access_control.mass_assignment`, CWE-915, severity high).
  Invoke when the user says "mass assignment", "check for mass
  assignment", or when dispatched by `tally-scan-external`.
---

# Tally scanner: Mass assignment

Detects sinks where user-controlled data is passed to ORM or model
create/update methods without restricting which fields can be assigned.
Runs per-file in the target repo (as dispatched by the
`tally-scan-external` orchestrator, or standalone when the user invokes
this skill directly). Emits a JSON list of findings; the orchestrator or
the user submits them to Tally through the `submit_finding` MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `access_control.mass_assignment` |
| Primary CWE | `CWE-915` |
| OWASP 2025 category | `Broken Access Control` |
| Default severity | `high` |
| Parent label (dedup) | `Mass Assignment` |

Source: Taxonomy defined in internal TAL-148 planning.

## Detection matrix

### Python

- **Django ORM without field filtering**: `ModelForm` instantiated
  without `fields` or `exclude` in Meta, or `__all__` used as fields.
  `Model.objects.create(**request.data)` or `Model.objects.update(
  **request.POST)`.
- **DRF Serializer without field restrictions**: Serializer class
  without explicit `fields` or `exclude` in Meta, or with
  `fields = '__all__'`.
- **FastAPI/Pydantic model accepting all fields**: A Pydantic model
  passed directly from `@Body()` or `request.json()` to ORM without
  field-level validation.
- **Direct dictionary assignment**: `obj.__dict__.update(user_input)`
  or `obj.__setattr__` with request data.

Read `references/python.md` for vulnerable-vs-safe code patterns.

### PHP

- **Laravel Model without fillable/guarded**: Model class with no
  `$fillable` array and no `$guarded = ['*']`, then passed
  `Model::create($request->all())` or `$model->fill(
  $request->all())`.
- **Laravel using $request->all() directly**: passing full request
  array to ORM without field filtering.
- **Symfony form handling without field restrictions**: Form builder
  without explicit field whitelisting.

Read `references/php.md` for vulnerable-vs-safe code patterns.

### JavaScript

- **Express/Sequelize model create**: `Model.create(req.body)` passing
  full request body without filtering.
- **Sequelize instance update**: `instance.update(req.body)` with no
  field allowlist.
- **Mongoose direct assignment**: `new Model(req.body).save()` or
  `Model.findByIdAndUpdate(id, req.body)`.
- **Direct property assignment**: looping over request keys and
  assigning to model without validation.

Read `references/javascript.md` for vulnerable-vs-safe code patterns.

### TypeScript

- **NestJS DTO without field validation**: `@Body()` accepting a DTO
  that maps directly to model creation without explicit field
  decorators or validation rules.
- **Prisma create with request data**: `.create({data: req.body})`
  passing full request object.
- **Prisma update with request data**: `.update({data: req.body})`
  with no field filtering.
- **TypeORM repository save**: `repository.save(req.body)` without
  field restrictions.

Read `references/typescript.md` for vulnerable-vs-safe code patterns.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the sink call.
- `meta.code_snippet`: 2-6 lines of source containing the sink.
- `meta.reasoning`: one sentence explaining why the pattern is a mass
  assignment at this location.
- When the model or serializer definition is in the same file:
  `meta.taint_source` naming the request parameter or upstream
  variable that reaches the sink.

Set `confidence`:

- `confirmed` when the model/serializer lacks field restrictions and
  the sink receives request data in the same file.
- `probable` when the sink pattern matches and receives a request-like
  variable, but the model definition is in a different file.
- `potential` when the sink pattern is suspicious but the source is
  not obviously user-controlled.

## Output payload skeleton

Emit one JSON object per finding with these fixed fields for
`access_control.mass_assignment`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing the sink, fields at risk, and attacker impact>",
  "severity": "high",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-915"],
  "finding_type": ["vulnerability"],
  "rule_id": "access_control.mass_assignment",
  "meta": {
    "title": "<e.g. 'Mass assignment via unfiltered Model.create()'>",
    "owasp_name": "Broken Access Control",
    "remediation": "<per-finding; see remediation guidance below>",
    "code_snippet": "<2-6 lines of source containing the sink>",
    "taint_source": "<request parameter or upstream variable, when traceable>",
    "reasoning": "<one sentence explaining why the pattern is unsafe>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for the
full field list and validator behavior.

## Remediation guidance for the scanner

Write `meta.remediation` inline based on the actual library
observed in the code. Examples of good remediation strings:

- **Django ModelForm**: `Define explicit `fields` in the form's Meta
  class: `fields = ['username', 'email']`. Never use
  `fields = '__all__'`. This whitelist prevents assignment to
  sensitive fields like `is_staff` and `is_superuser`.`
- **DRF Serializer**: `Add an explicit `fields` tuple to the Meta
  class: `fields = ('id', 'username', 'email')`. Avoid `fields =
  '__all__'`, which exposes every model field to the serializer.`
- **FastAPI Pydantic**: `Create a separate input DTO with only the
  fields the endpoint accepts. Pass the DTO to the model constructor
  via `.dict()`: `user = User(**input_dto.dict())`. Do not pass
  `request.json()` directly.`
- **Laravel Eloquent**: `Add a `$fillable` array to the model listing
  only the fields users may set: `protected $fillable =
  ['username', 'email'];`. Use `$guarded = ['*']` to deny all by
  default, then whitelist safe fields.`
- **Sequelize**: `Pass an options object with `fields` to the create
  or update call: `Model.create({...}, {fields: ['name', 'email']}).
  Reject any property on the request body that is not in the
  allowlist.`
- **Prisma**: `Use the `select` and `omit` helpers to exclude sensitive
  fields from the response. For create/update, validate the incoming
  data shape against your data model before calling `.create()`.`

Keep it two to four sentences. Vague guidance ("use a whitelist") is
worse than no guidance.

## Common false positives

- **Internal API endpoints**: Admin-only or backend-to-backend
  endpoints with proper authorization checks do not expose mass
  assignment risk (the attacker cannot reach the endpoint).
- **Models with explicit $fillable/$guarded**: A Laravel model with
  `protected $fillable = ['name', 'email']` is safe even when passed
  `$request->all()`.
- **Serializers with explicit fields**: A DRF Serializer with
  `fields = ('id', 'username')` in Meta is safe.
- **DTOs with validation decorators**: NestJS DTOs decorated with
  `@IsString()`, `@IsEmail()`, etc. and explicitly listed in the DTO
  class are safe.
- **Test and seed data creation**: Hardcoded fixtures or factory
  builders used only in tests are not production sinks.
- **Constants and build-time values**: Models instantiated with
  compile-time constant data or framework defaults (not request data)
  are safe.

## References

- `references/python.md`: Python patterns for Django, DRF, FastAPI
  Pydantic.
- `references/php.md`: PHP patterns for Laravel Eloquent, Symfony.
- `references/javascript.md`: Node patterns for Express, Sequelize,
  Mongoose.
- `references/typescript.md`: TypeScript patterns for NestJS, Prisma,
  TypeORM.
