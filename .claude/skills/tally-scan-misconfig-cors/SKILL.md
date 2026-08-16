---
name: tally-scan-misconfig-cors
description: >
  Scan the target repo for CORS misconfiguration defects. Detects CORS
  policies that permit any origin, combined with credentials enabled, or that
  reflect unauthenticated request origins. Emits findings shaped for Tally MCP
  submission (rule_id `misconfig.cors`, CWE-942, severity medium). Invoke when
  the user says "CORS", "cross-origin", "origin reflection", "check for CORS
  misconfiguration", or when dispatched by `tally-scan-external`.
---

# Tally scanner: CORS misconfiguration

Detects misconfigurations in Cross-Origin Resource Sharing (CORS) policies
where Access-Control headers permit overly permissive origins or reflect
unauthenticated source origins. Runs per-file in the target repo (as dispatched
by the `tally-scan-external` orchestrator, or standalone when the user invokes
this skill directly). Emits a JSON list of findings; the orchestrator or the
user submits them to Tally through the `submit_finding` MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `misconfig.cors` |
| Primary CWE | `CWE-942` |
| OWASP 2025 category | `Security Misconfiguration` |
| Default severity | `medium` |
| Parent label (dedup) | `CORSMisconfig` |


## Detection matrix

### Python

Read `references/python.md` for vulnerable-vs-safe snippets.

Detect these sink categories:

- **django-cors-headers wildcard**: CORS configuration with wildcard origins
  or credentials enabled.
- **Flask-CORS wildcard origins**: CORS middleware with permissive origin
  lists and credentials support.
- **Starlette/FastAPI CORSMiddleware**: wildcard origins with credentials
  enabled.
- **Manual header reflection**: setting Access-Control-Allow-Origin to the
  request Origin header without validation.

### PHP

Read `references/php.md` for vulnerable-vs-safe snippets.

Detect these sink categories:

- **Laravel CORS wildcard**: allowed_origins with wildcard or credentials
  enabled.
- **Manual header reflection (PHP)**: reflecting the HTTP_ORIGIN header
  without validation.
- **Manual CORS with credentials**: wildcard origins combined with
  Access-Control-Allow-Credentials.

### JavaScript

Read `references/javascript.md` for vulnerable-vs-safe snippets.

Detect these sink categories:

- **Express cors middleware wildcard**: wildcard origins with credentials
  support.
- **Manual header reflection (Express)**: setting headers with unvalidated
  request origin.
- **Koa CORS middleware**: permissive CORS configuration or origin reflection.

### TypeScript

Read `references/typescript.md` for vulnerable-vs-safe snippets.

Detect these sink categories:

- **Express.js with typed cors**: same patterns as JavaScript; type
  declarations do not prevent misconfiguration.
- **NestJS CORS config**: CORS configuration with wildcard origin and
  credentials.
- **Fastify CORS plugin**: permissive origin configuration or reflection.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the CORS configuration or header
  setting.
- `meta.code_snippet`: 2-6 lines of source containing the configuration.
- `meta.reasoning`: one sentence explaining why the configuration is
  overly permissive.
- When traceable: `meta.taint_source` naming the origin or request
  parameter that reaches the header.

Set `confidence`:

- `confirmed` when a wildcard origin is explicitly set alongside credentials,
  or when origin reflection is traced from a request header in the same file.
- `probable` when a permissive CORS configuration is detected but it is
  unclear whether credentials are enabled.
- `potential` when CORS is permissive but the finding is on a file that may
  not directly serve credentials.

## Output payload skeleton

Emit one JSON object per finding with these fixed fields for
`misconfig.cors`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing the misconfiguration, why it is risky,
  and how an attacker can exploit it>",
  "severity": "medium",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-942"],
  "finding_type": ["misconfiguration"],
  "rule_id": "misconfig.cors",
  "meta": {
    "title": "<short human title, e.g. 'CORS allows any origin with
    credentials enabled'>",
    "owasp_name": "Security Misconfiguration",
    "remediation": "<per-finding; see remediation guidance
    below>",
    "code_snippet": "<2-6 lines of configuration or header code>",
    "reasoning": "<one sentence explaining the misconfiguration at this
    location>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for the full
field list and validator behavior.

## Remediation guidance for the scanner

Write `meta.remediation` inline based on the actual library
observed in the code. Use the safe patterns from the per-language
reference files to write specific, actionable remediation.

- Name the library and its specific safe API
- Show the exact placeholder style or query builder method
- Keep it two to four sentences

## Common false positives

- **CORS for development only**: CORS configured in dev/test/local files
  with wildcard and credentials enabled is a misconfiguration but lower risk
  if not deployed to production.
- **Wildcard origin without credentials**: `Access-Control-Allow-Origin: *`
  without credentials headers is permissive but not a credential-theft vector
  and may be intentional for public APIs.
- **Public API endpoints**: CORS set on public API endpoints serving any
  origin without sensitive data is not a vulnerability.
- **Origin validation in separate middleware**: CORS headers set via config
  but origin validation performed by a middleware or firewall rule not visible
  in the scanned file.
- **Constants and templates**: CORS configuration in module-level constants
  or template files representing safe development values with no user control.

## References

- `references/python.md`: Python patterns for django-cors-headers,
  Flask-CORS, Starlette/FastAPI CORSMiddleware.
- `references/php.md`: PHP patterns for Laravel cors config, manual headers,
  and origin reflection.
- `references/javascript.md`: Node.js patterns for Express cors middleware,
  Koa, and manual headers.
- `references/typescript.md`: TypeScript patterns for NestJS CORS, Express
  with typed config, and Fastify plugins.
