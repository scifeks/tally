---
name: tally-scan-access-control-open-redirect
description: >
  Scan the target repo for unvalidated redirect and forward defects.
  Detects redirect functions and HTTP Location headers that accept
  user-controlled URLs without domain allowlist validation. Emits
  findings shaped for Tally MCP submission (rule_id
  `access_control.open_redirect`, CWE-601, severity medium). Invoke
  when the user says "open redirect", "unvalidated redirect", "check
  for redirects", or when dispatched by `tally-scan-external`.
---

# Tally scanner: Open redirect (unvalidated redirect or forward)

Detects sinks where user-controlled URL data reaches a redirect or
Location header response without domain validation. Runs per-file in
the target repo (as dispatched by the `tally-scan-external`
orchestrator, or standalone when the user invokes this skill
directly). Emits a JSON list of findings; the orchestrator or the
user submits them to Tally through the `submit_finding` MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `access_control.open_redirect` |
| Primary CWE | `CWE-601` |
| OWASP 2025 category | `Broken Access Control` |
| Default severity | `medium` |
| Parent label (dedup) | `OpenRedirect` |

Source: `docs/roadmap/TAL-148/taxonomy.md` T3 row 25.

## Detection matrix

### Python

- **Django redirect with user URL**: `redirect(request.GET['next'])`,
  `redirect(request.POST['url'])`, or
  `HttpResponseRedirect(request.GET.get('redirect_to'))` without
  `url_has_allowed_host_and_scheme` validation on the result.
- **Flask redirect with user URL**: `redirect(request.args.get('url'))`
  without domain allowlist or `is_safe_url` check.
- **FastAPI RedirectResponse with user URL**:
  `RedirectResponse(url=query_params['next'])` without URL validation.
- **Django `url_has_allowed_host_and_scheme` called but return value
  ignored**: the function returns `True` or `False`, and the code
  calls it but does not check the result.

Defer to `references/python.md` for vulnerable-vs-safe snippets.

### PHP

- **Bare header with user URL**: `header('Location: ' .
  $_GET['url'])` without domain validation.
- **Laravel redirect without allowlist**:
  `redirect()->to($request->input('redirect'))` or
  `redirect($request->input('url'))` without validation.
- **WordPress redirect without validation**:
  `wp_redirect($_GET['redirect_to'])` without `wp_validate_redirect`
  check.
- **Symfony RedirectResponse with user URL**:
  `new RedirectResponse($request->query->get('url'))` without
  validation.

Defer to `references/php.md` for vulnerable-vs-safe snippets.

### JavaScript

- **Express res.redirect with user URL**: `res.redirect(req.query.url)`
  without domain validation.
- **res.redirect from request body**:
  `res.redirect(req.body.returnUrl)` without allowlist check.
- **Manual Location header set**: `res.set('Location',
  req.query.next).status(302).end()` without URL validation.

Defer to `references/javascript.md` for vulnerable-vs-safe snippets.

### TypeScript

- **NestJS @Redirect with user URL**: `@Redirect()` decorator with
  URL sourced from `@Query` or request body without validation.
- **res.redirect from query parameter**: `res.redirect(req.query
  .redirect as string)` without allowlist check.
- **Fastify reply.redirect with user URL**:
  `reply.redirect(request.query.url)` without validation.
- **Remix redirect helper**: `redirect(request.headers.get
  ('referer'))` without domain check.

Defer to `references/typescript.md` for vulnerable-vs-safe snippets.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the redirect call.
- `meta.code_snippet`: 2-6 lines of source containing the sink.
- `meta.reasoning`: one sentence explaining why the pattern is an
  open redirect at this location.
- When the taint source is in the same file:
  `meta.taint_source` naming the request parameter or upstream
  variable that reaches the sink.

Set `confidence`:

- `confirmed` when a taint source is traced from a request handler
  to the sink in the same file, or through a same-file helper.
- `probable` when the sink pattern matches and the value is
  clearly a variable (not a constant), but the source is inferred.
- `potential` when the sink is suspicious but the value is not
  obviously user-controlled.

## Output payload skeleton

Emit one JSON object per finding with these fixed fields for
`access_control.open_redirect`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing the sink, the source, and what
  an attacker can do>",
  "severity": "medium",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-601"],
  "finding_type": ["vulnerability"],
  "rule_id": "access_control.open_redirect",
  "meta": {
    "title": "<short human title, e.g. 'Open redirect via
    unvalidated query parameter'>",
    "owasp_name": "Broken Access Control",
    "remediation": "<per-finding, per D19; see remediation guidance
    below>",
    "code_snippet": "<2-6 lines of source containing the sink>",
    "taint_source": "<request parameter or upstream variable, when
    traceable>",
    "reasoning": "<one sentence explaining the defect at this
    location>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for
the full field list and validator behavior.

## Remediation guidance for the scanner

Per D19, write `meta.remediation` inline based on the actual
library observed in the code. Examples of good remediation
strings:

- **Django**: `Use Django's
  `url_has_allowed_host_and_scheme(url, allowed_hosts=['example
  .com'])` and check the return value before redirecting. This
  function validates that the URL has an allowed host and scheme
  (http or https).`
- **Flask**: `Use `werkzeug.security.url_has_allowed_host_and_schemes
  (url, allowed_hosts=['example.com'])` or implement an allowlist
  of permitted redirect destinations and validate against it before
  calling `redirect()`.`
- **Laravel**: `Parse the URL and validate the host against an
  allowlist of permitted domains before passing to
  `redirect()->to()`. Alternatively, use named routes:
  `redirect(route('dashboard'))` instead of user-supplied URLs.`
- **Express**: `Validate the redirect destination: parse the URL
  with `new URL(userUrl)`, check that `url.hostname` is in your
  allowlist, and only then pass to `res.redirect()`. For
  same-origin redirects, use relative paths only.`
- **WordPress**: `Always wrap user-supplied redirect URLs with
  `wp_validate_redirect(url, admin_url())` and use its return value
  before calling `wp_redirect()`.`

Keep it two to four sentences. Vague guidance ("validate the URL")
is worse than no guidance.

## Common false positives

- **Hardcoded redirect targets**: `redirect('/dashboard')`,
  `redirect('https://trusted.example.com/login')` with no user
  input are safe.
- **Redirect to framework URL builder**: `redirect(url_for
  ('dashboard'))`, `redirect(reverse('login'))`, `redirect(route
  ('home'))` are safe by design.
- **Relative-path-only redirects**: `redirect(f'/profile/{user_id
  }')` or `redirect('../previous-page')` where the URL has no
  protocol or domain are safe if the path segment is validated.
- **Allowlist-validated URLs**: `if url_host in ALLOWED_HOSTS:
  redirect(url)` is safe when the allowlist check is performed and
  its result is verified.
- **OAuth callback validation**: redirects to URLs registered in an
  OAuth provider configuration (e.g. GitHub app registered redirect
  URIs) are safe by design.
- **Django settings constant**: `redirect(settings.LOGIN_URL)`,
  `redirect(settings.LOGIN_REDIRECT_URL)` are safe when the
  constant is not reassigned from request data.

## References

- `references/python.md`: Python patterns for Django, Flask, FastAPI.
- `references/php.md`: PHP patterns for Laravel, WordPress, Symfony,
  raw PHP.
- `references/javascript.md`: Node patterns for Express, manual
  headers.
- `references/typescript.md`: TypeScript patterns for NestJS, Fastify,
  Remix.
