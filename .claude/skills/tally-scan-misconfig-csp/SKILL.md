---
name: tally-scan-misconfig-csp
description: >
  Scan the target repo for Content Security Policy (CSP) misconfiguration.
  Detects missing CSP headers, CSP headers set to permissive values (wildcards,
  unsafe-inline, unsafe-eval), and disabled CSP in middleware. Emits findings
  shaped for Tally MCP submission (rule_id `misconfig.csp`, CWE-693, severity
  medium). Invoke when the user says "CSP", "content security policy", "check
  for CSP", or when dispatched by `tally-scan-external`.
---

# Tally scanner: CSP misconfiguration

Detects web framework configurations and explicit header directives that set
permissive Content Security Policy values or omit CSP entirely. Runs per-file
in the target repo (as dispatched by the `tally-scan-external` orchestrator, or
standalone when the user invokes this skill directly). Emits a JSON list of
findings; the orchestrator or the user submits them to Tally through the
`submit_finding` MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `misconfig.csp` |
| Primary CWE | `CWE-693` |
| OWASP 2025 category | `Security Misconfiguration` |
| Default severity | `medium` |
| Parent label (dedup) | `CSPMisconfig` |

## Detection matrix

### Python

Read `references/python.md` for vulnerable-vs-safe snippets.

Detect these sink categories:

- **Django CSP middleware disabled**: CSP middleware not in the MIDDLEWARE
  list.
- **Django CSP permissive**: CSP_DEFAULT_SRC with wildcard or unsafe
  directives.
- **Flask-Talisman disabled**: Talisman initialized with CSP disabled.
- **Flask-Talisman permissive**: content_security_policy dict with wildcard or
  unsafe directives.
- **Starlette middleware missing**: CSP middleware absent from the middleware
  stack.

### PHP

Read `references/php.md` for vulnerable-vs-safe snippets.

Detect these sink categories:

- **Laravel middleware missing**: security middleware absent or not setting CSP
  header.
- **Laravel header permissive**: Content-Security-Policy header with wildcard
  or unsafe directives.
- **Symfony NelmioSecurityBundle**: CSP config with permissive directives.
- **Manual header() permissive**: header calls setting wildcard or unsafe CSP
  directives.

### JavaScript

Read `references/javascript.md` for vulnerable-vs-safe snippets.

Detect these sink categories:

- **Express helmet disabled**: contentSecurityPolicy set to false in config.
- **Express helmet permissive**: CSP config with wildcard or unsafe directives.
- **Koa helmet missing**: no CSP middleware or empty CSP header.
- **Fastify helmet disabled**: @fastify/helmet with CSP disabled.

### TypeScript

Read `references/typescript.md` for vulnerable-vs-safe snippets.

Detect these sink categories:

- **Express helmet permissive**: same as JavaScript patterns with type
  annotations.
- **NestJS helmet permissive**: helm integration with permissive config.
- **Koa with TypeScript**: same as JavaScript patterns.
- **Custom middleware permissive**: middleware setting wildcard or unsafe CSP
  directives.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the configuration line or middleware
  initialization.
- `meta.code_snippet`: 2-6 lines of source containing the misconfiguration.
- `meta.reasoning`: one sentence explaining why the CSP setting is permissive
  or missing.
- When the CSP value is hardcoded in the config or file: `meta.csp_value`
  naming the actual directive or configuration value observed.

Set `confidence`:

- `confirmed` when the CSP is explicitly set to a permissive value or missing
  from the middleware stack.
- `probable` when the configuration suggests CSP is not enforced but the exact
  setting is not visible in the scanned file.
- `potential` when the file indicates security headers may not be configured
  but the evidence is indirect.

## Output payload skeleton

Emit one JSON object per finding with these fixed fields for `misconfig.csp`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing the permissive CSP or missing CSP,
  and the risk of XSS or injection attacks not being mitigated>",
  "severity": "medium",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-693"],
  "finding_type": ["misconfiguration"],
  "rule_id": "misconfig.csp",
  "meta": {
    "title": "<short human title, e.g. 'CSP default-src set to wildcard'>",
    "owasp_name": "Security Misconfiguration",
    "remediation": "<per-finding; see remediation guidance
    below>",
    "code_snippet": "<2-6 lines of source containing the configuration
    or middleware>",
    "csp_value": "<the actual CSP directive value observed, e.g.
    'default-src: *' or 'unsafe-inline', when visible>",
    "reasoning": "<one sentence explaining why the CSP is misconfigured
    at this location>"
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

- **CSP configured in reverse proxy**: CSP headers set by nginx, Apache, or
  CDN configuration outside the app code are not visible in the scanned app
  files. Flag only the app configuration.
- **CSP in separate security middleware**: CSP set in a dedicated middleware
  module or middleware factory not visible in the current file. Verify the
  middleware is registered in the framework's middleware stack.
- **Report-only mode with enforcement**: Content-Security-Policy-Report-Only
  header alongside a strict enforcement policy (Content-Security-Policy) is
  safe when enforcement is the primary policy.
- **Development-only permissive settings**: Check file path for dev-only
  indicators (dev.py, development.js, .env.development) before flagging
  permissive CSP.
- **Test fixtures or mock configs**: Configuration in test files or fixtures
  (test_settings.py, __fixtures__/, mock config objects) does not affect
  production; do not flag unless the test data is shared with production.
- **Nonce or hash based policies**: CSP using nonces (`'nonce-*'`) or hashes
  (`'sha256-*'`) is safe even without strict default-src; the nonce or hash
  whitelists specific inline scripts or styles.

## References

- `references/python.md`: Python patterns for Django, Flask-Talisman, Starlette.
- `references/php.md`: PHP patterns for Laravel, Symfony, manual header calls.
- `references/javascript.md`: Node patterns for Express helmet, Koa, Fastify.
- `references/typescript.md`: TypeScript patterns for NestJS, Express with
  TypeScript, custom middleware.
