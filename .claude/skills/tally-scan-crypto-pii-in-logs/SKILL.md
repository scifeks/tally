---
name: tally-scan-crypto-pii-in-logs
description: >
  Scan the target repo for PII or sensitive data written to
  log output. Detects logging statements that include passwords,
  API tokens, credit card numbers, SSNs, session tokens, or
  full request bodies containing sensitive fields. Emits
  findings shaped for Tally MCP submission (rule_id
  crypto.pii_in_logs, CWE-532, severity medium). Invoke when
  the user says "PII in logs", "sensitive data in logs",
  "logging passwords", "check log statements", or when
  dispatched by tally-scan-external.
---

# Tally scanner: PII or sensitive data in logs

Detects sinks where PII or sensitive data reaches a logging
output without redaction. Runs per-file in the target repo (as
dispatched by the `tally-scan-external` orchestrator, or
standalone when the user invokes this skill directly). Emits a
JSON list of findings; the orchestrator or the user submits them
to Tally through the `submit_finding` MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `crypto.pii_in_logs` |
| Primary CWE | `CWE-532` |
| OWASP 2025 category | `Cryptographic Failures` |
| Default severity | `medium` |
| Parent label (dedup) | `PIIExposure` |

Source: `docs/roadmap/TAL-148/taxonomy.md` T3 row 6.

## Detection matrix

### Python

- **f-string with sensitive variable in logger call**:
  `logging.info(f"... {password} ...")`,
  `logger.debug(f"Token: {api_token}")`,
  `logging.warning(f"Card: {credit_card}")`.
- **Logging full request body**: `logger.info(request.data)`,
  `logging.debug(str(request.POST))`.
- **print with sensitive data**: `print(f"Token: {token}")`
  in production code paths (not test files).
- **Exception logging with sensitive args**:
  `logging.exception(f"Login failed: {password}")`.

Defer to `references/python.md` for vulnerable-vs-safe
snippets.

### PHP

- **Log facade with sensitive data**:
  `Log::info("Payment: " . $creditCard)`,
  `Log::debug("Auth: password=$password")`.
- **error_log with sensitive variables**:
  `error_log("Password: $password")`.
- **Logging full request**: `Log::info(json_encode(
  $request->all()))` where the request contains passwords or
  tokens.
- **Laravel Telescope in production**: logging full request
  bodies and responses in production, which captures passwords
  and tokens.

Defer to `references/php.md` for vulnerable-vs-safe snippets.

### JavaScript

- **console.log with sensitive data**:
  `console.log('Token:', token)`,
  `console.log('Password:', password)`.
- **Logger with full request body**:
  `logger.info({body: req.body})` where the body contains
  sensitive fields.
- **Structured logger with sensitive fields**:
  `winston.info({user})` or `pino.info({user})` where the
  user object contains password or token fields.
- **Error logging with sensitive context**:
  `logger.error('Auth failed', {password, token})`.

Defer to `references/javascript.md` for vulnerable-vs-safe
snippets.

### TypeScript

Same sinks as JavaScript with typed logger calls.

Defer to `references/typescript.md` for vulnerable-vs-safe
snippets.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the sink call.
- `meta.code_snippet`: 2-6 lines of source containing the
  sink.
- `meta.reasoning`: one sentence explaining why the pattern is
  a defect at this location.
- When the taint source is in the same file:
  `meta.taint_source` naming the request parameter or
  upstream variable that reaches the sink.

Set `confidence`:

- `confirmed` when a taint source is traced from a request
  handler to the sink in the same file, or through a same-file
  helper.
- `probable` when the sink pattern matches and the value is
  clearly a variable (not a constant), but the source is
  inferred.
- `potential` when the sink is suspicious but the value is
  not obviously user-controlled.

## Output payload skeleton

Emit one JSON object per finding with these fixed fields for
`crypto.pii_in_logs`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing the sink, the sensitive data, and the risk>",
  "severity": "medium",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-532", "CWE-200"],
  "finding_type": ["vulnerability"],
  "rule_id": "crypto.pii_in_logs",
  "meta": {
    "title": "<short human title, e.g. 'Password logged in login handler'>",
    "owasp_name": "Cryptographic Failures",
    "remediation": "<per-finding, per D19; see remediation guidance below>",
    "code_snippet": "<2-6 lines of source containing the sink>",
    "taint_source": "<request parameter or upstream variable, when traceable>",
    "reasoning": "<one sentence explaining the defect at this location>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md`
for the full field list and validator behavior.

## Remediation guidance for the scanner

Write `meta.remediation` inline based on the actual
logging framework observed in the code. Examples of good
remediation strings:

- **Python logging**: Log only identifiers, not values:
  `logging.info("Login attempt for user_id=%s", user_id)`.
  Never include passwords, tokens, or PII in log arguments.
- **PHP Log facade**: Log only the operation and a record
  identifier: `Log::info("Payment processed", ['order_id' =>
  $orderId])`. Never concatenate sensitive values into log
  messages.
- **Node.js logger with redaction**: Use structured logging
  with field redaction: `pino({ redact: ['req.headers
  .authorization', 'req.body.password'] })`. Log user IDs,
  not user objects.
- **Full request body**: Instead of logging the full request
  body, log only the route and request ID. If debugging
  requires body content, log a sanitized subset that excludes
  password and token fields.

Keep it two to four sentences. Vague guidance ("redact the
data") is worse than no guidance.

## Common false positives

- **Logging identifiers only**: `logger.info("User %s logged
  in", user_id)` where `user_id` is a numeric ID, not PII.
- **Test and development code**: `console.log` in test files
  or development-only code paths that do not run in
  production.
- **Redacted logging**: structured loggers with configured
  redaction (e.g., `pino({ redact: [...] })`) that strip
  sensitive fields before writing.
- **Sanitized output**: logging a masked value
  (`"card: ****1234"`) rather than the full value.
- **Log level gating**: `logger.debug(...)` in a codebase
  that configures `INFO` or higher in production. Still flag
  if the production log level is not explicitly set.

## References

- `references/python.md`: Python patterns for logging
  libraries.
- `references/php.md`: PHP patterns for Log facade and
  error_log.
- `references/javascript.md`: Node.js patterns for console,
  winston, pino.
- `references/typescript.md`: TypeScript patterns for typed
  loggers.
