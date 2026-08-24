---
name: tally-scan-authentication-session-management
description: >
  Scan the target repo for broken session management defects.
  Detects session fixation (missing session ID regeneration after
  login), insecure session cookie flags (missing Secure, HttpOnly,
  SameSite), missing session timeouts, and session IDs exposed in
  URLs. Emits findings shaped for Tally MCP submission (rule_id
  `authentication.session_management`, CWE-384, severity high).
  Invoke when the user says "session fixation", "session
  management", "check session security", or when dispatched by
  `tally-scan-external`.
---

# Tally scanner: Broken session management

Detects code paths where session handling is vulnerable to fixation,
hijacking, or leakage due to missing regeneration, insecure cookie
flags, or absent timeouts. Runs per-file in the target repo (as
dispatched by the `tally-scan-external` orchestrator, or standalone
when the user invokes this skill directly). Emits a JSON list of
findings; the orchestrator or the user submits them to Tally
through the `submit_finding` MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `authentication.session_management` |
| Primary CWE | `CWE-384` |
| Secondary CWE | `CWE-613` |
| OWASP 2025 category | `Authentication Failures` |
| Default severity | `high` |
| Parent label (dedup) | `BrokenSession` |


## Detection matrix

### Python

- **Session fixation in Flask**: a login route that sets
  `session['user']` or `session['user_id']` without clearing and
  regenerating the session. Flask has no `session.regenerate()`;
  the safe pattern is `session.clear()` followed by repopulation.
- **Session fixation in Django**: a login view that sets
  `request.session[key]` directly without calling
  `request.session.cycle_key()`. The built-in `login()` function
  handles this automatically; flag only manual session assignment
  in authentication flows.
- **Insecure cookie flags (Flask)**: missing or `False` values for
  `SESSION_COOKIE_SECURE`, `SESSION_COOKIE_HTTPONLY`, or
  `SESSION_COOKIE_SAMESITE` in the Flask app config.
- **Insecure cookie flags (Django)**: missing or `False` values
  for `SESSION_COOKIE_SECURE`, `SESSION_COOKIE_HTTPONLY`, or
  `SESSION_COOKIE_SAMESITE` in Django settings.
- **Missing session timeout (Django)**: `SESSION_COOKIE_AGE` set
  to an excessively large value (over 86400) or absent (Django
  defaults to two weeks).

Read `references/python.md` for vulnerable-vs-safe code patterns.

### PHP

- **Session fixation**: `session_start()` followed by
  authentication logic without calling
  `session_regenerate_id(true)` after successful credential
  verification.
- **Insecure cookie flags**: `session.cookie_secure`,
  `session.cookie_httponly`, or `session.cookie_samesite` not set
  in `php.ini` or via `ini_set()` or `session_set_cookie_params()`
  before `session_start()`.
- **Session fixation in Laravel**: authentication flow that does
  not call `$request->session()->regenerate()` after login.
  `Auth::attempt()` handles this automatically; flag only custom
  authentication implementations.
- **Session ID in URL**: `session.use_trans_sid = 1` or
  `session.use_only_cookies = 0` in configuration, which appends
  the session ID to URLs.

Read `references/php.md` for vulnerable-vs-safe code patterns.

### JavaScript

- **Session fixation in Express**: a login handler that sets
  `req.session.user = userData` without calling
  `req.session.regenerate(callback)` first. The `regenerate`
  method destroys the old session and creates a new one.
- **Insecure cookie flags**: `express-session` configuration
  missing `secure: true`, `httpOnly: true`, or
  `sameSite: 'strict'` (or `'lax'`) in the `cookie` options.
- **Missing session expiry**: no `maxAge` set in the session
  cookie configuration, causing the cookie to persist
  indefinitely as a session cookie.
- **MemoryStore in production**: using the default
  `express-session` MemoryStore without a persistent store
  adapter (connect-redis, connect-mongo, etc.) in production
  code. MemoryStore leaks memory and loses sessions on restart.

Read `references/javascript.md` for vulnerable-vs-safe code
snippets.

### TypeScript

- **Session fixation in Express (typed)**: same Express patterns
  apply; TypeScript does not prevent session fixation at the type
  level.
- **Session fixation in NestJS**: a login guard or controller
  that writes session data without regenerating the session.
  NestJS uses `express-session` under the hood; the fix is the
  same `req.session.regenerate()` call.
- **Insecure cookie flags in NestJS**: `NestExpressApplication`
  session configuration missing secure cookie options.

Read `references/typescript.md` for vulnerable-vs-safe code
snippets.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the session assignment or
  configuration site.
- `meta.code_snippet`: 2-6 lines of source containing the sink.
- `meta.reasoning`: one sentence explaining why the pattern is a
  session management defect at this location.
- When the session is set in a login handler:
  `meta.taint_source` naming the authentication context (e.g.
  "login route at /auth/login").

Set `confidence`:

- `confirmed` when the login flow is visible in the same file and
  no regeneration call exists between credential check and session
  assignment.
- `probable` when session configuration is missing secure flags
  but the session middleware is clearly in use.
- `potential` when session assignment exists but the authentication
  context is ambiguous.

## Output payload skeleton

Emit one JSON object per finding with these fixed fields for
`authentication.session_management`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing the session defect>",
  "severity": "high",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-384", "CWE-613"],
  "finding_type": ["vulnerability"],
  "rule_id": "authentication.session_management",
  "meta": {
    "title": "<short title, e.g. 'Session fixation in login handler'>",
    "owasp_name": "Authentication Failures",
    "remediation": "<per-finding>",
    "code_snippet": "<2-6 lines of source>",
    "taint_source": "<auth context, when traceable>",
    "reasoning": "<one sentence explaining the defect>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for
the full field list and validator behavior.

## Remediation guidance for the scanner

Write `meta.remediation` inline based on the actual
framework observed in the code. Examples of good remediation
strings:

- **Flask session fixation**: `Call session.clear() before setting
  the new user identity after successful authentication. Flask
  does not have a dedicated regenerate method; clearing and
  repopulating achieves the same result.`
- **Django session fixation**: `Call
  request.session.cycle_key() after authenticating the user.
  This preserves session data while issuing a new session ID.
  The built-in django.contrib.auth.login() does this
  automatically; use it instead of manual session assignment.`
- **PHP session fixation**: `Call
  session_regenerate_id(true) immediately after successful
  credential verification. The true argument deletes the old
  session file.`
- **Express session fixation**: `Call
  req.session.regenerate(callback) before writing user data
  to the session. Move the session.user assignment into the
  regenerate callback.`
- **Insecure cookie flags**: `Set secure: true, httpOnly: true,
  and sameSite: 'lax' (or 'strict') in the session cookie
  configuration. The secure flag requires HTTPS; set it in
  production and guard with a conditional in development.`

Keep it two to four sentences. Vague guidance ("regenerate the
session") is worse than no guidance.

## Common false positives

- **Built-in auth functions**: `django.contrib.auth.login()`,
  Laravel's `Auth::attempt()`, and Passport.js `req.logIn()` all
  regenerate the session automatically. Do not flag login flows
  that delegate to these functions.
- **Non-authentication session writes**: setting a preference
  (`session['theme'] = 'dark'`) or a CSRF token in the session is
  not a fixation vector. Only flag session writes in
  authentication contexts.
- **Development-only settings**: `SESSION_COOKIE_SECURE = False`
  behind an `if DEBUG` or `if not app.config['PRODUCTION']` guard
  is acceptable for local development. Still flag if no production
  guard exists.
- **API-only services**: services that use only stateless JWT or
  token authentication and never create server-side sessions do
  not have session management defects. Confirm no session
  middleware is loaded before skipping.

## References

- `references/python.md`: Flask and Django session patterns.
- `references/php.md`: PHP native and Laravel session patterns.
- `references/javascript.md`: Express session patterns.
- `references/typescript.md`: NestJS and typed Express patterns.
