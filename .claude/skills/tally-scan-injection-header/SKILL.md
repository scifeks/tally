---
name: tally-scan-injection-header
description: >
  Scan the target repo for HTTP header injection defects. Detects user
  input placed into response headers without newline validation, allowing
  attackers to inject arbitrary headers or split the HTTP response. Emits
  findings shaped for Tally MCP submission (rule_id `injection.header`,
  CWE-113, severity medium). Invoke when the user says "header injection",
  "response splitting", "check for header injection", or when dispatched by
  `tally-scan-external`.
---

# Tally scanner: HTTP header injection

Detects sinks where user-controlled data reaches an HTTP response header
without stripping or validating newline characters. Runs per-file in the
target repo (as dispatched by the `tally-scan-external` orchestrator, or
standalone when the user invokes this skill directly). Emits a JSON list of
findings; the orchestrator or the user submits them to Tally through the
`submit_finding` MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `injection.header` |
| Primary CWE | `CWE-113` |
| Secondary CWE | `CWE-644` |
| OWASP 2025 category | `Injection` |
| Default severity | `medium` |
| Parent label (dedup) | `Header Injection` |


## Detection matrix

### Python

- **Direct header assignment**: `response['X-Custom'] = user_input`
  or `response.headers['X-Custom'] = user_input` without checking for
  newlines. Common in Django and Flask.
- **Redirect with user URL**: `redirect(url)` where `url` is
  request-derived. Some frameworks strip newlines, some do not; check
  framework behavior.
- **Content-Disposition filename**: `response['Content-Disposition'] =
  f'attachment; filename={filename}'` without newline stripping.
- **Location header**: `response['Location'] = user_url` or
  `response.redirect(user_url)`.

Read `references/python.md` for vulnerable-vs-safe code patterns.

### PHP

- **header() with user data**: `header("Location: " . $url)` or
  `header("X-Custom: " . $user_input)` where input is not validated.
- **setcookie() with user name or value**: `setcookie($user_name, $value)`
  without newline checks.
- **header("Refresh")**: `header("Refresh: 5; url=" . $url)` with
  user-controlled URL.

Read `references/php.md` for vulnerable-vs-safe code patterns.

### JavaScript

- **Express/Node.js setHeader**: `res.setHeader('X-Custom', userInput)`
  without sanitization. Modern versions (v14+) auto-strip newlines, but
  older code may not.
- **Redirect with user URL**: `res.redirect(userInput)` without validation.
- **writeHead with user data**: `res.writeHead(302, {'Location':
  userInput})`.
- **Set-Cookie**: `res.setHeader('Set-Cookie', userInput)`.

Read `references/javascript.md` for vulnerable-vs-safe code patterns.

### TypeScript

- Same sinks as JavaScript apply on the Node.js runtime.
- Express types and middleware for TypeScript projects.

Read `references/typescript.md` for vulnerable-vs-safe code patterns.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the sink call.
- `meta.code_snippet`: 2-6 lines of source containing the sink.
- `meta.reasoning`: one sentence explaining why the pattern permits
  header injection at this location.
- When the taint source is in the same file:
  `meta.taint_source` naming the request parameter or upstream variable
  that reaches the sink.

Set `confidence`:

- `confirmed` when a taint source is traced from a request handler to the
  sink in the same file, or through a same-file helper.
- `probable` when the sink pattern matches and the value is clearly a
  variable (not a constant), but the source is inferred.
- `potential` when the sink is suspicious but the value is not obviously
  user-controlled.

## Output payload skeleton

Emit one JSON object per finding with these fixed fields for
`injection.header`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing the sink, the source, and what an attacker can do>",
  "severity": "medium",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-113", "CWE-644"],
  "finding_type": ["vulnerability"],
  "rule_id": "injection.header",
  "meta": {
    "title": "<short human title, e.g. 'Header injection via user URL in redirect'>",
    "owasp_name": "Injection",
    "remediation": "<per-finding; see remediation guidance below>",
    "code_snippet": "<2-6 lines of source containing the sink>",
    "taint_source": "<request parameter or upstream variable, when traceable>",
    "reasoning": "<one sentence explaining why newlines in the value enable the defect>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for the full
field list and validator behavior.

## Remediation guidance for the scanner

Write `meta.remediation` inline based on the actual framework or
library observed in the code. Examples of good remediation strings:

- **Django**: `Use Django's built-in redirect helpers which validate URLs:
  from django.shortcuts import redirect; return redirect(url_obj). If the
  URL must be user-controlled, validate it against an allowlist of domains
  or parse it to strip any embedded newlines.`
- **Flask**: `Use url_for() for internal redirects: return
  redirect(url_for('endpoint', id=id)). For external URLs, validate the
  scheme and domain before setting the Location header.`
- **Express**: `Node.js res.redirect() and res.setHeader() in modern
  versions strip \\r and \\n automatically, but never rely on this. Validate
  or sanitize user input: use a URL parser and reject URLs with embedded
  newlines.`
- **PHP header()**: `Validate the URL before passing to header(). Use
  filter_var($url, FILTER_VALIDATE_URL) and check that parse_url() yields
  only the expected components. Never concatenate user input directly.`
- **Generic**: `Remove or encode any \\r (0x0D) and \\n (0x0A) bytes from
  the user input before placing it in a response header. Better: use an
  allowlist to validate the input's format (e.g., ensure a URL matches an
  expected pattern).`

Keep it two to four sentences. Vague guidance ("sanitize the input") is
worse than no guidance.

## Common false positives

- **Static-string headers with no user content**: `response['X-Version'] =
  '1.0.0'` is safe.
- **Framework middleware that auto-strips newlines**: Modern Node.js
  (v14+) automatically removes CR/LF from header values. Check framework
  documentation; do not assume.
- **URL-encoded values**: newlines in a percent-encoded URL (e.g.,
  `%0d%0a`) are encoded and safe to include in headers; the browser does
  not interpret them as control characters.
- **Allowlist-validated URLs**: if the code checks the URL against an
  explicit allowlist of domains before setting the header, it is safe.
- **Internal-only headers not derived from user input**: headers set from
  configuration or constants are safe.

## References

- `references/python.md`: Python patterns for Django, Flask, and stdlib.
- `references/php.md`: PHP patterns for header(), setcookie(), and
  redirect().
- `references/javascript.md`: Node.js patterns for Express and stdlib
  http module.
- `references/typescript.md`: TypeScript patterns for Express and
  type-wrapped Node.js.
