---
name: tally-scan-misconfig-framework-defaults
description: >
  Scan the target repo for framework defaults and debug-in-production
  misconfiguration. Detects DEBUG flags enabled, default secret keys,
  default admin credentials, and verbose error display settings in
  production-bound code. Emits findings shaped for Tally MCP submission
  (rule_id `misconfig.framework_defaults`, CWE-1188, severity medium).
  Invoke when the user says "debug mode", "framework defaults", "check
  for DEBUG", "hardcoded secrets", or when dispatched by
  `tally-scan-external`.
---

# Tally scanner: framework defaults and debug in production

Detects insecure default configuration settings in application frameworks
that expose sensitive information or enable dangerous behavior in
production. Runs per-file in the target repo (as dispatched by the
`tally-scan-external` orchestrator, or standalone when the user invokes
this skill directly). Emits a JSON list of findings; the orchestrator or
the user submits them to Tally through the `submit_finding` MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `misconfig.framework_defaults` |
| Primary CWE | `CWE-1188` |
| OWASP 2025 category | `Security Misconfiguration` |
| Default severity | `medium` |
| Parent label (dedup) | `FrameworkDefaults` |

Insecure Default Initialization of Resource, the correct primary weakness
for hardcoded defaults and debug-mode flags.

## Detection matrix

### Python

Read `references/python.md` for vulnerable-vs-safe snippets.

Detect these sink categories:

- **Django DEBUG setting**: DEBUG flag set to True in production settings.
- **Django SECRET_KEY**: SECRET_KEY set to development defaults or hardcoded
  values.
- **Django ALLOWED_HOSTS**: ALLOWED_HOSTS permissively configured.
- **Flask debug mode**: debug flag enabled in production code paths.
- **Flask secret_key**: secret_key set to common defaults or short strings.
- **FastAPI/Starlette debug mode**: debug flag enabled in production
  constructors.

### PHP

Read `references/php.md` for vulnerable-vs-safe snippets.

Detect these sink categories:

- **Laravel APP_DEBUG**: debug flag enabled in production environments.
- **Laravel APP_KEY**: APP_KEY set to defaults or empty values.
- **Laravel APP_ENV**: environment set to development values in production.
- **Symfony APP_ENV and APP_DEBUG**: debug settings or dev environments in
  production configuration.
- **WordPress WP_DEBUG**: debug flag enabled in wp-config.php in production.

### JavaScript

Read `references/javascript.md` for vulnerable-vs-safe snippets.

Detect these sink categories:

- **Express NODE_ENV**: NODE_ENV not set to production in deployment.
- **Express error handler**: verbose error handlers exposing stack traces.
- **Next.js debug flags**: debug mode settings in configuration used in
  production.
- **Koa/Fastify debug mode**: debug flag or verbose logging in production
  configuration.

### TypeScript

Read `references/typescript.md` for vulnerable-vs-safe snippets.

Detect these sink categories:

- **NestJS ConfigModule**: debug flag enabled in production code paths.
- **NestJS default secrets**: hardcoded secret values instead of environment
  variables.
- **Express patterns (typed)**: same NODE_ENV and error handler patterns as
  JavaScript.
- **Next.js patterns (typed)**: debug flags in config files used in
  production.
- **Hardcoded config values**: development values in production TypeScript
  config files.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the configuration line that sets
  the insecure default.
- `meta.code_snippet`: 2-6 lines of source containing the insecure
  setting.
- `meta.reasoning`: one sentence explaining why this configuration is
  insecure in production.
- When the configuration is conditionally set: `meta.taint_source`
  naming the environment variable or configuration key that controls
  the insecure value.

Set `confidence`:

- `confirmed` when the insecure setting is hardcoded or loaded from a
  constant in production-bound code paths.
- `probable` when the setting matches the insecure pattern but is
  conditionally set based on an environment variable with no explicit
  production check.
- `potential` when the configuration file is ambiguous (e.g., a config
  template that may or may not be used in production).

## Output payload skeleton

Emit one JSON object per finding with these fixed fields for
`misconfig.framework_defaults`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing the insecure setting, the framework
  affected, and the production risk>",
  "severity": "medium",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-1188"],
  "finding_type": ["misconfiguration"],
  "rule_id": "misconfig.framework_defaults",
  "meta": {
    "title": "<short human title, e.g. 'DEBUG mode enabled in production
    Django settings'>",
    "owasp_name": "Security Misconfiguration",
    "remediation": "<per-finding remediation specific to the framework
    and setting; see remediation guidance below>",
    "code_snippet": "<2-6 lines of source containing the insecure
    setting>",
    "reasoning": "<one sentence explaining the production risk at this
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

- **Development settings files**: files explicitly named for non-production
  use (e.g., `settings/local.py`, `settings/dev.py`, `.env.local`,
  `.env.development`, `config/dev.js`) are safe and must not be flagged.
- **Test configurations**: test-only settings files (e.g.,
  `settings/test.py`, `.env.testing`) are safe and must not be flagged.
- **Secret keys loaded from environment variables**: `SECRET_KEY =
  os.getenv('SECRET_KEY')` or `app.secret_key = os.environ['SECRET_KEY']`
  are safe patterns even if the variable name is visible in the code.
- **DEBUG set conditionally from environment**: `DEBUG =
  os.getenv('DEBUG', 'False').lower() == 'true'` with a safe default is
  safe.
- **Docker Compose and CI configuration files**: non-deployed configuration
  used only for local development or testing is safe and must not be
  flagged.
- **Example and template configuration files**: `.env.example`,
  `config.template.php`, or `sample-config.js` marked as templates are
  safe and must not be flagged.
- **Config files with production environment checks**: if the file
  explicitly checks `APP_ENV=production` before applying settings, it is
  safe.

## References

- `references/python.md`: Python patterns for Django, Flask, FastAPI,
  Starlette.
- `references/php.md`: PHP patterns for Laravel, Symfony, WordPress.
- `references/javascript.md`: Node patterns for Express, Next.js, Koa,
  Fastify.
- `references/typescript.md`: TypeScript patterns for NestJS, Express with
  TypeScript, Next.js with TypeScript.
