---
name: tally-scan-xss-reflected
description: >
  Scan the target repo for reflected cross-site scripting (XSS)
  defects. Detects same-request rendering of user input without
  escaping: query parameters echoed in HTML responses, form data
  interpolated into templates, request headers rendered in error
  pages, and URL path segments reflected into page content. Emits
  findings shaped for Tally MCP submission (rule_id
  `xss.reflected`, CWE-79, severity high). Invoke when the user
  says "reflected XSS", "check for reflected XSS", or when
  dispatched by `tally-scan-external`.
---

# Tally scanner: Reflected XSS

Detects sinks where data from the current HTTP request (query
parameters, form fields, headers, URL path segments) reaches an
HTML rendering context in the same response without output escaping.
Runs per-file in the target repo (as dispatched by the
`tally-scan-external` orchestrator, or standalone when the user
invokes this skill directly). Emits a JSON list of findings; the
orchestrator or the user submits them to Tally through the
`submit_finding` MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `xss.reflected` |
| Primary CWE | `CWE-79` |
| OWASP 2025 category | `Injection` |
| Default severity | `high` |
| Parent label (dedup) | `XSS` |


## Detection matrix

### Python

- **Flask f-string response**: `return f"<p>Results for:
  {request.args.get('q')}</p>"`. Any response that interpolates a
  request parameter into HTML without `html.escape()`.
- **Django HttpResponse with request data**: `return HttpResponse(
  f"<p>{request.GET['q']}</p>")`. Direct HTML construction from
  request parameters.
- **`render_template_string()` with request data**:
  `render_template_string("<p>" + request.args['q'] + "</p>")`.
  Building a template from request input and rendering it.
- **FastAPI HTMLResponse with query param**:
  `return HTMLResponse(f"<p>{query}</p>")` where `query` comes
  from a query parameter or path variable.
- **Django template with request context**: `{{ request.GET.q }}`
  rendered with `|safe` or inside `{% autoescape off %}`.

Read `references/python.md` for vulnerable-vs-safe code patterns.

### PHP

- **Echo of superglobal**: `echo $_GET['search']` or
  `echo $_POST['name']` or `echo $_SERVER['HTTP_REFERER']`
  without `htmlspecialchars()`.
- **Blade with request()**: `{!! request()->input('q') !!}` in
  Laravel Blade. Safe form: `{{ request()->input('q') }}`.
- **Twig with app.request**: `{{ app.request.get('q')|raw }}` in
  Symfony. Safe form: `{{ app.request.get('q') }}`.
- **WordPress echo of $_GET**: `echo '<p>' . $_GET['msg'] .
  '</p>'` without `esc_html()`.
- **Error page reflection**: `echo "Page not found: " .
  $_SERVER['REQUEST_URI']` in custom error handlers.

Read `references/php.md` for vulnerable-vs-safe code patterns.

### JavaScript

- **Express res.send with query**: `res.send("<p>Search: " +
  req.query.q + "</p>")`. Direct HTML response from request data.
- **EJS unescaped with request data**: `<%- req.query.search %>`
  in an Express/EJS template.
- **Client-side DOM with URL data**: `document.getElementById(
  "output").innerHTML = new URLSearchParams(location.search).get(
  "q")`. Reading from `location.search`, `location.hash`, or
  `document.referrer` into an HTML sink.
- **`document.write()` with URL data**: `document.write(
  location.hash.slice(1))`.

Read `references/javascript.md` for vulnerable-vs-safe code
snippets.

### TypeScript

- **Express res.send with typed params**: `res.send(
  `<p>${req.query.q}</p>`)` in an Express route. TypeScript types
  do not escape the value.
- **Angular route param to HTML**: extracting a route parameter
  via `ActivatedRoute` and passing it to
  `bypassSecurityTrustHtml()`.
- Same JavaScript patterns apply on the Node runtime.

Read `references/typescript.md` for vulnerable-vs-safe code
snippets.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the HTML rendering sink.
- `meta.code_snippet`: 2-6 lines of source containing the sink.
- `meta.reasoning`: one sentence explaining why the pattern is a
  reflected XSS at this location (must mention the request source).
- When the request parameter is identifiable:
  `meta.taint_source` naming the parameter, header, or URL
  component that reaches the sink.

Set `confidence`:

- `confirmed` when a request parameter is traced to an unescaped
  HTML sink in the same handler or through a same-file helper.
- `probable` when the sink pattern matches and the variable is
  clearly request-derived (naming convention like `query`,
  `search`, `input`), but the source assignment is not visible.
- `potential` when the sink is unescaped and the handler receives
  request data, but the specific parameter is not traceable.

## Output payload skeleton

Emit one JSON object per finding with these fixed fields for
`xss.reflected`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing the sink, the request source,
and what an attacker can do>",
  "severity": "high",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-79"],
  "finding_type": ["vulnerability"],
  "rule_id": "xss.reflected",
  "meta": {
    "title": "<short title, e.g. 'Reflected XSS via search
query parameter'>",
    "owasp_name": "Injection",
    "remediation": "<per-finding; see guidance below>",
    "code_snippet": "<2-6 lines of source>",
    "taint_source": "<request parameter name, when traceable>",
    "reasoning": "<one sentence explaining the defect>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for
the full field list and validator behavior.

## Remediation guidance for the scanner

Write `meta.remediation` inline based on the actual
library or framework observed. Examples:

- **Flask f-string**: `Use render_template() with Jinja2
  auto-escaping instead of building HTML strings. If a plain
  string response is needed, call markupsafe.escape() on every
  interpolated request value.`
- **Django HttpResponse**: `Use render() with a template instead
  of building HTML in HttpResponse(). Django templates auto-escape
  by default.`
- **PHP echo $_GET**: `Wrap the value: echo htmlspecialchars(
  $_GET['search'], ENT_QUOTES, 'UTF-8'). Apply encoding at every
  output point, not at input.`
- **Laravel Blade {!! !!}**: `Replace {!! request()->input('q')
  !!} with {{ request()->input('q') }}. Blade's double braces
  apply htmlspecialchars() automatically.`
- **Express res.send**: `Use a template engine with auto-escaping
  (EJS <%= %>, Pug, Handlebars). If building HTML strings
  directly, use a library like he or escape-html to encode values
  before interpolation.`
- **Client-side DOM**: `Use textContent instead of innerHTML to
  display URL-derived data. If HTML structure is needed, sanitize
  with DOMPurify.sanitize() first.`

Keep it two to four sentences.

## Common false positives

- **Auto-escaped template output**: `{{ request.GET.q }}` in
  Django, `{{ request()->input('q') }}` in Blade, and
  `<%= req.query.q %>` in EJS auto-escape by default. Do not
  flag these.
- **JSON responses**: `return JsonResponse({"q": request.GET[
  "q"]})` or `res.json({q: req.query.q})` is not an XSS sink.
  JSON content-type prevents browser HTML parsing.
- **Redirect responses**: `return redirect(url)` or
  `res.redirect(url)` is not a rendering sink (but may be an open
  redirect; that is a different skill).
- **Content-type headers**: Responses with `Content-Type:
  text/plain` or `application/json` are not XSS sinks even if
  they contain request data.
- **Server-side logging**: `logger.info(f"Query: {request.args[
  'q']}")` is not an XSS sink (but may be a log injection; that
  is out of scope for this skill).

## References

- `references/python.md`: Python patterns for Flask, Django,
  FastAPI with request parameters.
- `references/php.md`: PHP patterns for superglobals, Blade,
  Twig, WordPress with request data.
- `references/javascript.md`: JavaScript patterns for Express,
  client-side DOM, and URL-sourced data.
- `references/typescript.md`: TypeScript patterns for Express
  and Angular with request parameters.
