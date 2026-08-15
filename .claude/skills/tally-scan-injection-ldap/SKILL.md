---
name: tally-scan-injection-ldap
description: >
  Scan the target repo for LDAP injection defects. Detects string-formatted
  LDAP filters, unparameterized LDAP filter queries, and filter operations
  that interpolate user input without escaping. Emits findings shaped for
  Tally MCP submission (rule_id `injection.ldap`, CWE-90, severity high).
  Invoke when the user says "LDAP injection", "LDAPi", "check for LDAP
  injection", or when dispatched by `tally-scan-external`.
---

# Tally scanner: LDAP injection

Detects sinks where user-controlled data reaches an LDAP filter interpreter
without proper escaping. Runs per-file in the target repo (as dispatched by
the `tally-scan-external` orchestrator, or standalone when the user invokes
this skill directly). Emits a JSON list of findings; the orchestrator or the
user submits them to Tally through the `submit_finding` MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `injection.ldap` |
| Primary CWE | `CWE-90` |
| Secondary CWE | `CWE-74` |
| OWASP 2025 category | `Injection` |
| Default severity | `high` |
| Parent label (dedup) | `LDAPInjection` |

Source: `docs/roadmap/TAL-148/taxonomy.md` T3 row 5.

## Detection matrix

### Python

- **String-formatted filter (python-ldap)**: an f-string, `.format()`, or
  `%`-formatting that interpolates a request-derived value into an LDAP
  filter string passed to `search_s()`, `search()`, `search_ext()`, or an
  equivalent call on an `LDAPObject`.
- **Concatenated filter (python-ldap)**: `+`-concatenation of an LDAP filter
  string with a request-derived value passed to any LDAP search method.
- **String-formatted filter (ldap3)**: f-string or `.format()` in the filter
  argument to `connection.search()`. The safe form escapes the value with
  `ldap3.utils.escape_filter_chars()` or uses a filter builder.
- **Dynamic filter construction (ldap3)**: template literals or string
  concatenation in filter arguments without escaping. The safe form wraps
  values in `escape_filter_chars()`.

Defer to `references/python.md` for vulnerable-vs-safe snippets.

### PHP

- **Interpolated ldap_search**: string interpolation or concatenation into
  the filter argument of `ldap_search()`, `ldap_list()`, `ldap_read()`,
  or `ldap_search_ext()`. Safe form uses `ldap_escape()` with the
  `LDAP_ESCAPE_FILTER` flag.
- **sprintf-built filter**: filter string constructed with `sprintf()` or
  `.` concatenation where a request-derived value is not escaped. Safe form
  passes the value through `ldap_escape()` before assembly.
- **Direct filter interpolation**: `"(uid=$userInput)"` style. Safe form is
  `"(uid=" . ldap_escape($userInput, '', LDAP_ESCAPE_FILTER) . ")"`.

Defer to `references/php.md` for vulnerable-vs-safe snippets.

### JavaScript

- **Template literal filter (ldapjs)**: `` client.search(base, {filter:
  `(uid=${userId})`}) `` or `+` concatenation where `userId` is
  request-sourced. Safe form escapes the value before templating or uses an
  object-based filter builder.
- **String concatenation filter**: `"(uid=" + userInput + ")"` passed as the
  filter option. Safe form escapes or uses a filter-building library.

Defer to `references/javascript.md` for vulnerable-vs-safe snippets.

### TypeScript

- **Template literal filter (ldapjs)**: same as JavaScript with typed
  `ldapjs` bindings.
- **Dynamic filter in typed code**: same concatenation patterns as JS,
  type-annotated. Safe form escapes the value before assembly.

Defer to `references/typescript.md` for vulnerable-vs-safe snippets.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the sink call.
- `meta.code_snippet`: 2-6 lines of source containing the sink.
- `meta.reasoning`: one sentence explaining why the pattern is an LDAP
  injection at this location.
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
`injection.ldap`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing the sink, the source, and what an
    attacker can do>",
  "severity": "high",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-90", "CWE-74"],
  "finding_type": ["vulnerability"],
  "rule_id": "injection.ldap",
  "meta": {
    "title": "<short human title, e.g. 'LDAP injection via f-string in
      auth handler'>",
    "owasp_name": "Injection",
    "remediation": "<per-finding, per D19; see remediation guidance below>",
    "code_snippet": "<2-6 lines of source containing the sink>",
    "taint_source": "<request parameter or upstream variable, when
      traceable>",
    "reasoning": "<one sentence explaining the defect at this location>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for the full
field list and validator behavior.

## Remediation guidance for the scanner

Per D19, write `meta.remediation` inline based on the actual library
observed in the code. Examples of good remediation strings:

- **python-ldap**: `Escape the user input with
  ldap.filter.escape_filter_chars() before interpolating into the filter
  string: ldap.search_s(base, scope,
  '(uid=' + ldap.filter.escape_filter_chars(user_id) + ')').`
- **ldap3**: `Use ldap3.utils.escape_filter_chars() to escape the value
  before building the filter string: connection.search(base,
  '(uid=' + escape_filter_chars(user_id) + ')').`
- **PHP (ldap_search)**: `Use ldap_escape() with LDAP_ESCAPE_FILTER on
  user input before interpolating into the filter: ldap_search($conn,
  $base, '(uid=' . ldap_escape($uid, '', LDAP_ESCAPE_FILTER) . ')').`
- **ldapjs**: `Use ldapjs' built-in escape or manually escape the value
  before templating: client.search(base, {filter: '(uid=' +
  escapeLdapFilterValue(userId) + ')'}).`

Keep it two to four sentences. Vague guidance ("escape the filter") is
worse than no guidance.

## Common false positives

- **Static-string filters with no interpolation**: `search(base, scope,
  '(objectClass=*)') ` is safe regardless of the driver.
- **Filters from allowlisted sources**: filter strings built from module-
  level constants or enum values with no user reachability are safe.
  Confirm the value is not later reassigned from a request.
- **Structured filter builders**: `ldap3`'s `filter_format()` or equivalent
  builder libraries handle escaping internally. The safe form uses the
  builder, not string interpolation.
- **Session-stored values**: values retrieved from a session or database
  that originated from a prior, complete authentication are safe if they
  have no subsequent user modification.

## References

- `references/python.md`: Python patterns for python-ldap and ldap3.
- `references/php.md`: PHP patterns for ldap_* functions and ldap_escape.
- `references/javascript.md`: Node patterns for ldapjs.
- `references/typescript.md`: TypeScript patterns for ldapjs.
