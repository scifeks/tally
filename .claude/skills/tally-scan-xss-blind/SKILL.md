---
name: tally-scan-xss-blind
description: >
  Scan the target repo for blind cross-site scripting (XSS) defects.
  Detects user-submitted data that is stored and later rendered in
  admin panels, internal dashboards, log viewers, or email templates
  without escaping. The attacker cannot observe the execution
  directly; the payload fires in a different user's session. Emits
  findings shaped for Tally MCP submission (rule_id `xss.blind`,
  CWE-79, severity high). Invoke when the user says "blind XSS",
  "out-of-band XSS", "check for blind XSS", or when dispatched by
  `tally-scan-external`.
---

# Tally scanner: Blind XSS

Detects sinks where user-submitted data is stored and later rendered
in a context the original user cannot observe: admin panels, internal
dashboards, log viewers, email notifications, PDF reports, or
support-ticket interfaces. The attacker does not see the payload
execute; it fires when an admin or internal user views the stored
data. Runs per-file in the target repo (as dispatched by the
`tally-scan-external` orchestrator, or standalone when the user
invokes this skill directly). Emits a JSON list of findings; the
orchestrator or the user submits them to Tally through the
`submit_finding` MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `xss.blind` |
| Primary CWE | `CWE-79` |
| OWASP 2025 category | `Injection` |
| Default severity | `high` |
| Parent label (dedup) | `XSS` |


## Detection matrix

Blind XSS has two halves: the write path (user input stored) and
the read path (admin/internal template renders it). Either half
alone is insufficient. Flag when both halves are visible or when
the read path renders user-sourced data from a model/table known
to accept public input.

### Python

- **Admin template with |safe on user field**: a Django admin
  template or custom admin view that renders a model field with
  `|safe` or `mark_safe()`, where the model stores user-submitted
  data (contact forms, feedback, support tickets).
- **Email template with user data**: `render_to_string(
  'email.html', {'message': ticket.body})` followed by
  `send_mail()`, where the email template uses `|safe` or
  `{% autoescape off %}` on the user-submitted field.
- **Log viewer rendering stored entries**: a view that reads log
  entries (containing user input like usernames, search queries,
  or request paths) and renders them in HTML with `|safe` or
  `Markup()`.
- **PDF/report generation with user data**: Jinja2 templates used
  by WeasyPrint or xhtml2pdf that include user-submitted fields
  without escaping.

Read `references/python.md` for vulnerable-vs-safe code patterns.

### PHP

- **Admin panel echoing user submissions**: `echo
  $submission->message` in an admin controller or view without
  `htmlspecialchars()`, where `$submission` stores public form
  data.
- **WordPress admin unescaped user meta**: `echo
  get_user_meta($user_id, 'bio', true)` in an admin screen
  without `esc_html()`.
- **CMS admin listing**: Blade `{!! $ticket->description !!}` or
  Twig `{{ feedback.body|raw }}` in an admin-only template that
  renders data submitted by public users.
- **Email template with user data**: `Mail::send('email', [
  'body' => $contact->message], ...)` where the email Blade
  template uses `{!! $body !!}`.

Read `references/php.md` for vulnerable-vs-safe code patterns.

### JavaScript

- **Admin React dashboard with dangerouslySetInnerHTML**: an
  admin-facing React component that renders user-submitted data
  (tickets, feedback, form responses) via
  `dangerouslySetInnerHTML`.
- **Internal tool with innerHTML**: `element.innerHTML =
  ticket.description` in an internal support-tool UI where
  `ticket.description` was submitted by an external user.
- **Log viewer component**: a component that fetches log entries
  (containing user input) from an API and renders them with
  `innerHTML` or `<%- %>`.
- **Email HTML template (server-side)**: a Node mailer template
  that interpolates user-submitted data without escaping:
  `html: `<p>${ticket.body}</p>``

Read `references/javascript.md` for vulnerable-vs-safe code
snippets.

### TypeScript

- **Angular admin with bypassSecurityTrustHtml**: an admin
  component that fetches user-submitted records from an API and
  renders them via `bypassSecurityTrustHtml()`.
- **React admin dashboard (TSX)**: same as JavaScript React
  pattern in an admin-facing component.

Read `references/typescript.md` for vulnerable-vs-safe code
snippets.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the internal rendering
  sink (the admin template, email template, or log viewer).
- `meta.code_snippet`: 2-6 lines of source containing the sink.
- `meta.reasoning`: one sentence explaining why the pattern is a
  blind XSS (must mention the internal/admin rendering context
  and the user-submitted data source).
- When the data model or write path is identifiable:
  `meta.taint_source` naming the model, table, or API endpoint
  that stores the user-submitted data.

Set `confidence`:

- `confirmed` when both the write path (user input to storage)
  and read path (storage to unescaped admin/internal render) are
  visible in the same file or connected through a traceable model.
- `probable` when the read path renders a model field without
  escaping, and the model is clearly user-facing (names like
  `Ticket`, `Feedback`, `ContactForm`, `Comment`), but the write
  path is not in the same file.
- `potential` when an admin or internal template renders data
  without escaping, but the data source is ambiguous.

## Output payload skeleton

Emit one JSON object per finding with these fixed fields for
`xss.blind`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing the internal rendering sink,
the user-submitted data source, and what an attacker can do>",
  "severity": "high",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-79"],
  "finding_type": ["vulnerability"],
  "rule_id": "xss.blind",
  "meta": {
    "title": "<short title, e.g. 'Blind XSS in admin ticket
viewer'>",
    "owasp_name": "Injection",
    "remediation": "<per-finding; see guidance below>",
    "code_snippet": "<2-6 lines of source>",
    "taint_source": "<model or table storing user data, when
traceable>",
    "reasoning": "<one sentence explaining the defect>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for
the full field list and validator behavior.

## Remediation guidance for the scanner

Write `meta.remediation` inline based on the actual
library or framework observed. Examples:

- **Django admin template**: `Remove the |safe filter from the
  admin template. Admin templates need the same escaping as
  public-facing ones. If rich text display is needed, sanitize
  with bleach.clean() at write time.`
- **Django email template**: `Remove |safe or {% autoescape off %}
  from the email template. Use {{ variable }} with auto-escaping.
  If HTML emails must include user content, sanitize with
  bleach.clean() before rendering.`
- **Laravel admin Blade**: `Replace {!! $ticket->description !!}
  with {{ $ticket->description }} in the admin template. Admin
  views are high-value targets; unescaped output here lets an
  attacker compromise admin sessions.`
- **WordPress admin screen**: `Wrap the output: echo esc_html(
  get_user_meta($user_id, 'bio', true)). Admin screens process
  user-submitted data and need the same escaping as the public
  site.`
- **React admin component**: `Remove dangerouslySetInnerHTML from
  the admin component. Render text directly: <div>
  {ticket.description}</div>. Admin dashboards are high-value
  targets for blind XSS. If HTML rendering is needed, sanitize
  with DOMPurify.sanitize() first.`
- **Node email template**: `Use a template engine with
  auto-escaping for HTML emails. If building HTML strings, call
  escape-html on every interpolated user value.`

Keep it two to four sentences.

## Common false positives

- **Auto-escaped admin templates**: Django admin templates using
  `{{ variable }}` (without `|safe`) auto-escape by default.
  Blade `{{ $variable }}` in admin views is safe. Do not flag
  these.
- **Admin-only data**: If the data rendered in the admin panel was
  entered by admins (not public users), the blind XSS attack path
  does not exist. Confirm the data source accepts public input.
- **Plain-text email**: Email sent as `text/plain` (not
  `text/html`) cannot execute scripts. Do not flag plain-text
  email templates.
- **PDF rendering with escaped content**: PDF generators that
  use auto-escaping templates are safe. Confirm the template
  uses `|safe`, `|raw`, or `{!! !!}` before flagging.
- **JSON API responses consumed by admin SPA**: If the admin
  frontend is a SPA that renders API data through React/Angular
  with default escaping, the API endpoint is not the sink. The
  sink is the frontend component (flag that instead if it uses
  `dangerouslySetInnerHTML` or `bypassSecurityTrustHtml`).

## References

- `references/python.md`: Python patterns for admin templates,
  email templates, and log viewers.
- `references/php.md`: PHP patterns for admin panels, CMS admin
  views, and email templates.
- `references/javascript.md`: JavaScript patterns for admin
  dashboards, internal tools, and email templates.
- `references/typescript.md`: TypeScript patterns for Angular
  and React admin components.
