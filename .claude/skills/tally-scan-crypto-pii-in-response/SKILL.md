---
name: tally-scan-crypto-pii-in-response
description: >
  Scan the target repo for PII or sensitive data exposed
  in API responses. Detects serializers, response DTOs,
  and controller responses that include sensitive fields
  (SSN, credit card, date of birth, medical data,
  password hashes) without redaction. Emits findings
  shaped for Tally MCP submission (rule_id
  crypto.pii_in_response, CWE-200, severity medium).
  Invoke when the user says "PII in response",
  "sensitive data exposure", "data leakage in API",
  "check for PII", or when dispatched by
  tally-scan-external.
---

# Tally scanner: PII or sensitive data in responses

Detects sinks where sensitive user data is serialized into API responses
without redaction. Runs per-file in the target repo (as dispatched by the
`tally-scan-external` orchestrator, or standalone when the user invokes
this skill directly). Emits a JSON list of findings; the orchestrator or
the user submits them to Tally through the `submit_finding` MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `crypto.pii_in_response` |
| Primary CWE | `CWE-200` |
| OWASP 2025 category | `Cryptographic Failures` |
| Default severity | `medium` |
| Parent label (dedup) | `PIIExposure` |

Source: `docs/roadmap/TAL-148/taxonomy.md` T3 row 5.

## Detection matrix

### Python

- **Django REST serializer with `fields = '__all__'`** on a model that has
  sensitive columns (password, ssn, date_of_birth, credit_card,
  social_security_number).
- **FastAPI response model exposing sensitive fields**: a Pydantic model
  used as `response_model` that includes password, SSN, or financial data
  without `exclude`.
- **Flask jsonify with full model dump**: `jsonify(user.__dict__)` or
  `jsonify(user.to_dict())` where the model has sensitive fields.
- **Raw dict response with sensitive keys**: returning a dict that
  includes `password`, `ssn`, `credit_card`, or `token` fields to the
  client.

Defer to `references/python.md` for vulnerable-vs-safe snippets.

### PHP

- **Laravel `toArray()` in response**: `response()->json(
  $user->toArray())` where the model has sensitive columns.
- **Laravel API Resource without field filtering**: a Resource that
  passes through `$this->password`, `$this->ssn`, or
  `$this->credit_card`.
- **Controller returning full model**: `return $user;` in a controller
  method, relying on implicit JSON serialization of all attributes.
- **Missing `$hidden` array**: Eloquent model without `$hidden` for
  sensitive fields like `password`, `remember_token`.

Defer to `references/php.md` for vulnerable-vs-safe snippets.

### JavaScript

- **Express `res.json(user)`**: where `user` is a database object with
  sensitive fields.
- **GraphQL resolver returning full object**: resolver that returns the
  database record without field selection.
- **Serialization of `req.user`**: middleware or handler that sends the
  full user object (including tokens, password hashes) in a response.

Defer to `references/javascript.md` for vulnerable-vs-safe snippets.

### TypeScript

Same sinks as JavaScript. Additionally:

- **Response DTO that mirrors the database entity**: a TypeScript
  interface or class used for both database entity and API response
  without separating concerns.

Defer to `references/typescript.md` for vulnerable-vs-safe snippets.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the sink call.
- `meta.code_snippet`: 2-6 lines of source containing the sink.
- `meta.reasoning`: one sentence explaining why the pattern is a defect
  at this location.
- When the taint source is in the same file: `meta.taint_source` naming
  the request parameter or upstream variable that reaches the sink.

Set `confidence`:

- `confirmed` when a taint source is traced from a request handler to the
  sink in the same file, or through a same-file helper.
- `probable` when the sink pattern matches and the value is clearly a
  variable (not a constant), but the source is inferred.
- `potential` when the sink is suspicious but the value is not obviously
  user-controlled.

## Output payload skeleton

Emit one JSON object per finding with these fixed fields for
`crypto.pii_in_response`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing the sink and exposure>",
  "severity": "medium",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-200"],
  "finding_type": ["vulnerability"],
  "rule_id": "crypto.pii_in_response",
  "meta": {
    "title": "<short human title, e.g. 'PII exposed in user profile response'>",
    "owasp_name": "Cryptographic Failures",
    "remediation": "<per-finding, per D19; see remediation guidance below>",
    "code_snippet": "<2-6 lines of source containing the sink>",
    "taint_source": "<request parameter or upstream variable, when traceable>",
    "reasoning": "<one sentence explaining the defect at this location>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for the full
field list and validator behavior.

## Remediation guidance for the scanner

Write `meta.remediation` inline based on the actual library observed in
the code. Examples of good remediation strings:

- **Django REST serializer**: `Define an explicit fields list in the
  serializer Meta class. Remove sensitive fields or use a separate
  response serializer: fields = ['id', 'name', 'email'].`
- **FastAPI response model**: `Create a separate Pydantic response model
  that excludes sensitive fields. Use response_model=UserResponse
  instead of response_model=User.`
- **Laravel model**: `Add sensitive fields to the model's $hidden array:
  protected $hidden = ['password', 'remember_token', 'ssn'].`
- **Express response**: `Destructure only the fields you need: const { id,
  name, email } = user; res.json({ id, name, email }).`

Keep it two to four sentences. Vague guidance ("remove sensitive fields")
is worse than no guidance.

## Common false positives

- **Admin-only endpoints**: endpoints restricted to admin users that
  intentionally expose full user data for management purposes.
- **Self-profile endpoints**: a user viewing their own full profile where
  PII exposure is expected.
- **Internal service-to-service responses**: responses between internal
  microservices behind a network boundary, not exposed to end users.
- **Redacted fields**: fields that appear in the response but are masked
  (e.g., `"ssn": "***-**-1234"`).

## References

- `references/python.md`: Python patterns for Django REST, FastAPI,
  Flask.
- `references/php.md`: PHP patterns for Laravel models and resources.
- `references/javascript.md`: Node patterns for Express, GraphQL.
- `references/typescript.md`: TypeScript patterns for response DTOs.
