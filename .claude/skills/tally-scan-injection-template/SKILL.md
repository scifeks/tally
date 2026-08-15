---
name: tally-scan-injection-template
description: >
  Scan the target repo for server-side template injection (SSTI) defects.
  Detects template rendering functions and expression languages that
  evaluate user-controlled strings as template code. Recognizes Jinja2,
  Mako, Twig, Blade, EJS, Pug, Handlebars, and Nunjucks sinks that accept
  dynamic template input without sandboxing. Emits findings shaped for
  Tally MCP submission (rule_id `injection.template`, CWE-1336, severity
  critical). Invoke when the user says "template injection", "SSTI",
  "check for SSTI", or when dispatched by `tally-scan-external`.
---

# Tally scanner: template injection

Detects sinks where user-controlled data reaches a template interpreter
without sandboxing or escaping. Runs per-file in the target repo (as
dispatched by the `tally-scan-external` orchestrator, or standalone
when the user invokes this skill directly). Emits a JSON list of
findings; the orchestrator or the user submits them to Tally through the
`submit_finding` MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `injection.template` |
| Primary CWE | `CWE-1336` |
| Secondary CWE | `CWE-94` |
| OWASP 2025 category | `Injection` |
| Default severity | `critical` |
| Parent label (dedup) | `TemplateInjection` |

Source: `docs/roadmap/TAL-148/taxonomy.md` T3 row 3.

## Detection matrix

### Python

- **Jinja2 `render_template_string`**: Flask's
  `render_template_string(user_input)` or Jinja2's direct call with an
  unescaped string. Safe form uses `render_template('file.html',
  var=user_input)` where the template path is a literal.
- **Jinja2 `Template` direct instantiation**: `Template(user_input)
  .render()` or `Environment().from_string(user_input).render()`. Safe
  form passes user data through the context, not the template source.
- **Mako `Template` constructor**: `MakoTemplate(user_input).render()`
  or `TemplateLookup().get_template(user_input).render()`. Safe form
  uses a template filename or passes data through the context.
- **String template evaluation**: `string.Template(user_input)
  .substitute(...)` when the input is not already a known constant.

Defer to `references/python.md` for vulnerable-vs-safe snippets.

### PHP

- **Twig `createTemplate`**: `$twig->createTemplate($userInput)
  ->render()`. Safe form uses `$twig->render('file.html', $context)`.
- **Laravel Blade `compileString`**: `Blade::compileString($userInput)`
  followed by rendering. Safe form uses Blade templates as files, not
  compiled from request data.
- **Smarty `fetch` with string prefix**: `$smarty->fetch('string:' .
  $userInput)` or `$smarty->display('string:' . $userInput)`. Safe form
  loads templates from files only.

Defer to `references/php.md` for vulnerable-vs-safe snippets.

### JavaScript

- **EJS `render` with dynamic template**: `ejs.render(userInput, data)`
  or `ejs.renderFile(userInput, data)` when the template source is
  request-derived. Safe form renders from a literal filename and passes
  data through the `data` parameter.
- **Pug `render` with dynamic source**: `pug.render(userInput)`.
  Safe form uses `pug.renderFile('file.pug')` and passes data through
  the options.
- **Handlebars `compile` with dynamic input**: `Handlebars.compile(
  userInput)` then executing the result. Safe form defines templates as
  literal strings or loads from files.
- **Nunjucks `renderString` with dynamic template**: `nunjucks
  .renderString(userInput, data)`. Safe form uses `nunjucks.render(
  'file.html', data)`.

Defer to `references/javascript.md` for vulnerable-vs-safe snippets.

### TypeScript

- **Nunjucks `renderString` (typed)**: Same as JavaScript, with type
  declarations available.
- **EJS (typed)**: Same as JavaScript, with type definitions.
- **Angular `bypassSecurityTrustHtml`**: Returning a template string
  that includes user data without prior escaping or validation. Safe
  form escapes user input before combining with template markup.
- **Server-side template rendering libraries**: TypeORM, Sequelize, or
  other libraries that render templates dynamically.

Defer to `references/typescript.md` for vulnerable-vs-safe snippets.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the sink call.
- `meta.code_snippet`: 2-6 lines of source containing the sink.
- `meta.reasoning`: one sentence explaining why the pattern is an SSTI
  at this location.
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
`injection.template`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing the sink, the source, and what an attacker can do>",
  "severity": "critical",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-1336", "CWE-94"],
  "finding_type": ["vulnerability"],
  "rule_id": "injection.template",
  "meta": {
    "title": "<short human title, e.g. 'SSTI via Jinja2 render_template_string'>",
    "owasp_name": "Injection",
    "remediation": "<per-finding, per D19; see remediation guidance below>",
    "code_snippet": "<2-6 lines of source containing the sink>",
    "taint_source": "<request parameter or upstream variable, when traceable>",
    "reasoning": "<one sentence explaining the defect at this location>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for
the full field list and validator behavior.

## Remediation guidance for the scanner

Per D19, write `meta.remediation` inline based on the actual
library observed in the code. Examples of good remediation
strings:

- **Flask Jinja2**: `Use render_template('template.html', var=user_input)
  where the template filename is a literal string. Never pass user input
  to render_template_string().`
- **Jinja2 direct**: `Pass user data through the template context, not
  the template source. Use Environment().from_string('static {{ var }}')
  .render(var=user_input), not from_string(user_input).`
- **Mako**: `Load templates from files: TemplateLookup(
  directories=['templates']).get_template('mytemplate.html'). If the
  template source must be dynamic, use a SandboxedLookup.`
- **Twig (PHP)**: `Load templates as files: $twig->render('file.html',
  $context). Never pass request data to createTemplate().`
- **Laravel Blade**: `Store templates as files in resources/views/. Use
  view('template', $data) instead of Blade::compileString($userInput).`
- **EJS (Node)**: `Render from a file: ejs.renderFile('views/template.ejs',
  data, callback). Pass user input only through the data parameter.`
- **Nunjucks**: `Use nunjucks.render('file.html', data) or
  nunjucks.renderString('static {{ var }}', {var: data}), never
  nunjucks.renderString(userInput).`

Keep it two to four sentences. Vague guidance ("use a template file")
is worse than no guidance.

## Common false positives

- **Static template strings with no interpolation**: `render_template(
  'SELECT * FROM users')` is safe regardless of the engine.
- **Template rendering with user data in context only**:
  `render_template('file.html', name=user_name)`,
  `ejs.renderFile('file.ejs', {name: user_name})`, and Blade's
  `view('template', $data)` are safe by design.
- **Literal template strings with placeholder syntax**: `render(
  'Hello {{ name }}', data)` where the template literal is not
  interpolated from user input is safe.
- **File-path templates where the file path is validated**:
  `renderFile(allowed_templates[user_choice])` where `allowed_templates`
  is an allowlist is safe, provided the choice itself is not used in
  path traversal.
- **Sandboxed template environments**: `SandboxedEnvironment()` in Jinja2
  or equivalent sandboxing in other engines restricts what code can
  execute, reducing but not eliminating risk.

## References

- `references/python.md`: Python patterns for Jinja2, Mako, Django
  templates, string.Template.
- `references/php.md`: PHP patterns for Twig, Blade, Smarty.
- `references/javascript.md`: Node patterns for EJS, Pug, Handlebars,
  Nunjucks.
- `references/typescript.md`: TypeScript patterns for Nunjucks, EJS,
  Angular.
