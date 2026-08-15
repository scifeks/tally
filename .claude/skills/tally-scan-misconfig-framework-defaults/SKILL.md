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

Source: `docs/roadmap/TAL-148/taxonomy.md` T3 row 31. CWE-1188 is
Insecure Default Initialization of Resource, the correct primary weakness
for hardcoded defaults and debug-mode flags.

## Detection matrix

### Python

- **Django DEBUG setting**: `DEBUG = True` in production settings files
  or conditionally set to True without explicit environment guards.
- **Django SECRET_KEY**: `SECRET_KEY` set to `django-insecure-*` prefix
  (development marker), common tutorial values like `'secret'`,
  `'insecure'`, or empty string.
- **Django ALLOWED_HOSTS**: `ALLOWED_HOSTS = ['*']` in production settings.
- **Flask debug mode**: `app.debug = True` or `app.run(debug=True)` in
  production code paths.
- **Flask secret_key**: `app.secret_key` set to short or common strings
  like `'dev'`, `'secret'`, `'changeme'`, or derived from `os.urandom`
  with a short seed in production settings.
- **FastAPI debug mode**: `debug=True` in `FastAPI()` constructor in
  production settings files.
- **Starlette debug mode**: `debug=True` in `Starlette()` constructor in
  production code paths.

Defer to `references/python.md` for vulnerable-vs-safe snippets.

### PHP

- **Laravel APP_DEBUG**: `APP_DEBUG=true` in `.env` or config files
  loaded in production, or set to true in config arrays.
- **Laravel APP_KEY**: `APP_KEY` set to `base64:` prefix with a default
  value, empty string, or common tutorial values.
- **Laravel APP_ENV**: `APP_ENV=local` or `APP_ENV=development` in
  production deployment environments.
- **Symfony APP_ENV**: `APP_ENV=dev` in production `.env` files.
- **Symfony APP_DEBUG**: `APP_DEBUG=1` in production environment.
- **Symfony APP_SECRET**: `APP_SECRET` set to common defaults or empty.
- **WordPress WP_DEBUG**: `WP_DEBUG` set to true in `wp-config.php` in
  production deployments.

Defer to `references/php.md` for vulnerable-vs-safe snippets.

### JavaScript

- **Express NODE_ENV**: `NODE_ENV` not set to `production` in deployment
  configuration or conditionally set to a non-production value.
- **Express error handler**: verbose error handler middleware that prints
  stack traces to the client in production configuration.
- **Next.js debug flags**: debug or development mode settings in
  `next.config.js` used in production builds.
- **Koa/Fastify debug mode**: debug flag or verbose logging enabled in
  production configuration files.

Defer to `references/javascript.md` for vulnerable-vs-safe snippets.

### TypeScript

- **NestJS ConfigModule**: `debug: true` in ConfigModule configuration
  used in production code paths.
- **NestJS default secrets**: `JWT_SECRET`, session secrets, or API keys
  set to default or hardcoded strings instead of environment variables.
- **TypeScript Express patterns**: same `NODE_ENV` and error handler
  patterns as JavaScript Express.
- **TypeScript Next.js patterns**: debug flags in `next.config.js` or
  `.ts`/`.tsx` config files used in production builds.
- **Hardcoded config values**: development configuration values
  (localhost, debug flags, test credentials) included in production
  TypeScript config files.

Defer to `references/typescript.md` for vulnerable-vs-safe snippets.

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

Per D19, write `meta.remediation` inline based on the actual framework
observed in the code. Examples of good remediation strings:

- **Django DEBUG**: `Set DEBUG = False in production settings. Load this
  setting from an environment variable: DEBUG = os.getenv('DEBUG',
  'False').lower() == 'true'.`
- **Django SECRET_KEY**: `Generate a unique SECRET_KEY with
  django.core.management.utils.get_random_secret_key() and store it in
  the SECRET_KEY environment variable. Load it with SECRET_KEY =
  os.getenv('SECRET_KEY').`
- **Flask debug mode**: `Set app.debug = False and load the setting from
  the FLASK_ENV environment variable. Ensure the production deployment
  does not set FLASK_ENV=development.`
- **Laravel APP_DEBUG**: `Set APP_DEBUG=false in the production .env
  file. Never hardcode debug flags in config arrays for production
  deployments.`
- **Laravel APP_KEY**: `Generate a unique APP_KEY with php artisan
  key:generate and store it in the production .env file. Never use or
  rely on the base64: default.`
- **Express NODE_ENV**: `Set NODE_ENV=production in the deployment
  environment (container, systemd, or CI/CD). This disables verbose error
  pages and enables template caching.`
- **WordPress WP_DEBUG**: `Set WP_DEBUG to false in wp-config.php for
  production deployments. Do not enable debug logging in production.`

Keep it two to four sentences. Vague guidance ("disable debug mode") is
worse than no guidance.

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
