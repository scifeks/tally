---
name: tally-scan-xss-stored
description: >
  Scan the target repo for stored cross-site scripting (XSS) defects.
  Detects template renders and HTML outputs that display
  persistence-sourced data without escaping: mark_safe() on model
  fields, Blade {!! !!} on database columns, Twig |raw on stored
  values, and dangerouslySetInnerHTML with API responses. Emits
  findings shaped for Tally MCP submission (rule_id `xss.stored`,
  CWE-79, severity high). Invoke when the user says "stored XSS",
  "persistent XSS", "check for stored XSS", or when dispatched by
  `tally-scan-external`.
---

# Tally scanner: Stored XSS

Detects sinks where data retrieved from a persistence layer (database,
cache, file, or API response backed by a data store) reaches an HTML
rendering context without output escaping. Runs per-file in the target
repo (as dispatched by the `tally-scan-external` orchestrator, or
standalone when the user invokes this skill directly). Emits a JSON
list of findings; the orchestrator or the user submits them to Tally
through the `submit_finding` MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `xss.stored` |
| Primary CWE | `CWE-79` |
| OWASP 2025 category | `Injection` |
| Default severity | `high` |
| Parent label (dedup) | `XSS` |


## Detection matrix

### Python

- **`mark_safe()` on DB field**: `mark_safe(obj.field)` where `obj`
  comes from a queryset or database read. The `mark_safe()` call
  tells Django's template engine to skip auto-escaping.
- **`|safe` filter on model attribute**: `{{ post.body|safe }}` in
  a Django or Jinja2 template where the variable is a model field
  populated from user input.
- **`Markup()` on stored value**: `Markup(comment.text)` in
  Flask/Jinja2 marks a stored string as safe HTML, bypassing
  auto-escape.
- **f-string HTML with DB data**: `return HttpResponse(
  f"<div>{user.bio}</div>")` or `return f"<p>{row['comment']}</p>"`.
  Any response that interpolates a persistence-sourced value into
  HTML without `html.escape()`.
- **`render_template_string()` with DB data**: building a Jinja2
  template from stored data and rendering it.

Read `references/python.md` for vulnerable-vs-safe code patterns.

### PHP

- **Unescaped echo of DB column**: `echo $row['comment']` or
  `echo $post->body` without `htmlspecialchars()`. Safe form wraps:
  `echo htmlspecialchars($row['comment'], ENT_QUOTES, 'UTF-8')`.
- **Blade `{!! !!}` on model field**: `{!! $post->content !!}` in
  Laravel Blade renders the stored value without escaping. Safe
  form: `{{ $post->content }}`.
- **Twig `|raw` on stored data**: `{{ article.body|raw }}` in
  Symfony/Twig bypasses auto-escaping. Safe form omits the filter:
  `{{ article.body }}`.
- **WordPress unescaped output**: `echo get_post_meta($id, 'field',
  true)` or `echo $post->post_content` without `esc_html()` or
  `wp_kses()`.

Read `references/php.md` for vulnerable-vs-safe code patterns.

### JavaScript

- **`innerHTML` with API/DB data**: `element.innerHTML =
  data.comment` where `data` comes from a fetch/API call backed
  by a database.
- **React `dangerouslySetInnerHTML`**: `<div
  dangerouslySetInnerHTML={{__html: post.content}} />` where
  `post.content` originates from an API response.
- **EJS unescaped with DB data**: `<%- post.body %>` renders
  without escaping. Safe form: `<%= post.body %>`.
- **Handlebars triple-brace**: `{{{comment.text}}}` renders
  without escaping. Safe form: `{{comment.text}}`.
- **`insertAdjacentHTML()` with stored data**:
  `el.insertAdjacentHTML('beforeend', apiResponse.html)`.

Read `references/javascript.md` for vulnerable-vs-safe code
snippets.

### TypeScript

- **Angular `bypassSecurityTrustHtml()`**: `this.sanitizer.
  bypassSecurityTrustHtml(post.content)` where `post` comes from
  an API. Angular sanitizes by default; this call disables it.
- **React `dangerouslySetInnerHTML` (TSX)**: same as JavaScript;
  TypeScript type annotations do not prevent the unsafe render.
- **Express + template engine**: same as JavaScript patterns on
  the Node runtime.

Read `references/typescript.md` for vulnerable-vs-safe code
snippets.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the HTML rendering sink.
- `meta.code_snippet`: 2-6 lines of source containing the sink.
- `meta.reasoning`: one sentence explaining why the pattern is a
  stored XSS at this location (must mention the persistence source).
- When the persistence read is in the same file:
  `meta.taint_source` naming the model field, query result, or
  API response property that reaches the sink.

Set `confidence`:

- `confirmed` when a persistence read (DB query, API fetch, cache
  get) is traced to an unescaped HTML sink in the same file or
  through a same-file helper.
- `probable` when the template variable originates from a model
  field (naming convention or type hint suggests DB origin) but
  the query is not in the same file.
- `potential` when the sink is unescaped and the variable name
  suggests stored data, but the source is not traceable.

## Output payload skeleton

Emit one JSON object per finding with these fixed fields for
`xss.stored`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing the sink, the stored source,
and what an attacker can do>",
  "severity": "high",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-79"],
  "finding_type": ["vulnerability"],
  "rule_id": "xss.stored",
  "meta": {
    "title": "<short title, e.g. 'Stored XSS via unescaped
comment field'>",
    "owasp_name": "Injection",
    "remediation": "<per-finding; see guidance below>",
    "code_snippet": "<2-6 lines of source>",
    "taint_source": "<model field or query result, when traceable>",
    "reasoning": "<one sentence explaining the defect>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for
the full field list and validator behavior.

## Remediation guidance for the scanner

Write `meta.remediation` inline based on the actual
library or framework observed. Examples:

- **Django mark_safe**: `Remove the mark_safe() call and let
  Django's auto-escaping handle the output. If the field must
  contain HTML, sanitize it at write time with bleach.clean()
  before storing.`
- **Django |safe filter**: `Remove the |safe filter from the
  template. Django auto-escapes by default; removing |safe
  activates the protection. If trusted HTML is needed, sanitize
  at write time.`
- **Flask Markup()**: `Remove the Markup() wrapper. Jinja2
  auto-escapes by default in Flask. If the stored HTML is
  intentional, pass it through bleach.clean() before wrapping.`
- **Laravel Blade**: `Replace {!! $post->content !!} with
  {{ $post->content }}. Blade's double braces run
  htmlspecialchars() automatically. If HTML rendering is needed,
  sanitize at write time with a library like mews/purifier.`
- **PHP echo**: `Wrap the output: echo htmlspecialchars(
  $row['comment'], ENT_QUOTES, 'UTF-8'). Apply encoding at every
  output point.`
- **React dangerouslySetInnerHTML**: `Remove
  dangerouslySetInnerHTML. Render text directly as a JSX
  expression: <div>{post.content}</div>. React escapes string
  values by default. If HTML rendering is needed, sanitize with
  DOMPurify.sanitize() first.`
- **Angular bypassSecurityTrustHtml**: `Remove the
  bypassSecurityTrustHtml() call. Angular sanitizes by default.
  If trusted HTML is needed, sanitize server-side before the API
  returns it.`

Keep it two to four sentences.

## Common false positives

- **Auto-escaped template output**: `{{ variable }}` in Django,
  Jinja2, Blade, Twig, and Handlebars auto-escapes by default.
  Do not flag these.
- **Constant HTML fragments**: `mark_safe('<br>')` or
  `{!! '<hr>' !!}` with a string literal containing no user data
  is safe.
- **Sanitized before storage**: If the code calls
  `bleach.clean()`, `DOMPurify.sanitize()`, `htmlspecialchars()`,
  `wp_kses()`, or `strip_tags()` on the value before writing it
  to the database, and the sanitized value reaches the template,
  the output is safe.
- **Static seed data**: Data from migrations or seed scripts with
  hardcoded values (no user input path) is safe.
- **JSON API responses**: Returning stored data as JSON
  (`JsonResponse`, `res.json()`) is not an XSS sink. The
  vulnerability is in the HTML rendering.

## References

- `references/python.md`: Python patterns for Django, Flask/Jinja2,
  and template rendering with stored data.
- `references/php.md`: PHP patterns for Blade, Twig, WordPress,
  and raw echo with database values.
- `references/javascript.md`: JavaScript patterns for React, EJS,
  Handlebars, and DOM manipulation with API data.
- `references/typescript.md`: TypeScript patterns for Angular,
  React TSX, and Express templates with stored data.
