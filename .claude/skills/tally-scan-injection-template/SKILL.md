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


## Detection matrix

### Python

Read `references/python.md` for vulnerable-vs-safe snippets.

Detect these sink categories:

- **Flask template rendering**: render_template_string or direct template
  instantiation with user-supplied template source.
- **Jinja2 direct usage**: Template constructor or from_string with
  user-controlled template code.
- **Mako template rendering**: direct template instantiation or
  TemplateLookup with request-derived sources.
- **String template evaluation**: string.Template with user-supplied format
  strings.

### PHP

Read `references/php.md` for vulnerable-vs-safe snippets.

Detect these sink categories:

- **Twig createTemplate**: creating template instances from user input
  rather than loading from files.
- **Laravel Blade compileString**: rendering compiled template strings from
  request data.
- **Smarty string prefix**: using the string: prefix to render request-sourced
  template code.

### JavaScript

Read `references/javascript.md` for vulnerable-vs-safe snippets.

Detect these sink categories:

- **EJS render**: render or renderFile with user-supplied template source or
  filename.
- **Pug render**: render or renderFile with request-derived template data.
- **Handlebars compile**: compiling user-supplied template strings.
- **Nunjucks renderString**: evaluating request-sourced template code.

### TypeScript

Read `references/typescript.md` for vulnerable-vs-safe snippets.

Detect these sink categories:

- **Typed template engines**: EJS, Nunjucks, and other libraries used with
  user-supplied template sources regardless of type declarations.
- **Framework-specific bypasses**: Angular or other framework security
  bypasses when user data flows to trusted-HTML functions.
- **Dynamic template rendering**: TypeORM, Sequelize, or similar libraries
  rendering templates from user input.

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
    "remediation": "<per-finding; see remediation guidance below>",
    "code_snippet": "<2-6 lines of source containing the sink>",
    "taint_source": "<request parameter or upstream variable, when traceable>",
    "reasoning": "<one sentence explaining the defect at this location>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for
the full field list and validator behavior.

## Remediation guidance for the scanner

Write `meta.remediation` inline based on the actual library
observed in the code. Use the safe patterns from the per-language
reference files to write specific, actionable remediation.

- Name the library and its specific safe API
- Show the exact placeholder style or query builder method
- Keep it two to four sentences

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
