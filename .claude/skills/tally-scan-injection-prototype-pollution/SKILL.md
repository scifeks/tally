---
name: tally-scan-injection-prototype-pollution
description: >
  Scan the target repo for prototype pollution defects. Detects
  recursive merge and extend operations on objects with user input,
  deep clone libraries that traverse __proto__ or constructor,
  unsafe query string parsing, and Object.assign with user-controlled
  sources. Emits findings shaped for Tally MCP submission (rule_id
  `injection.prototype_pollution`, CWE-1321, severity high). Invoke
  when the user says "prototype pollution", "prototype pollution
  check", or when dispatched by `tally-scan-external`.
---

# Tally scanner: Prototype pollution

Detects sinks where user-controlled data can modify an object's
prototype chain or constructor, affecting all objects that inherit
from it. Runs per-file in the target repo (as dispatched by the
`tally-scan-external` orchestrator, or standalone when the user
invokes this skill directly). Emits a JSON list of findings; the
orchestrator or the user submits them to Tally through the
`submit_finding` MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `injection.prototype_pollution` |
| Primary CWE | `CWE-1321` |
| OWASP 2025 category | `Injection` |
| Default severity | `high` |
| Parent label (dedup) | `Prototype Pollution` |


## Detection matrix

### JavaScript

Read `references/javascript.md` for vulnerable-vs-safe snippets.

Detect these sink categories:

- **Recursive merge operations**: lodash merge variants, jQuery extend with
  deep flag, or custom merge functions that traverse nested objects
  without filtering prototype-chain keys.
- **Object mutation on shared state**: assigning user-supplied objects to
  module-level or request-shared variables using Object.assign or direct
  property assignment.
- **Deep clone libraries**: JSON parsing followed by recursive merge of
  user-supplied data into existing objects.
- **Query string parsing**: parsing URL parameters or request bodies with
  parsers that permit __proto__ or constructor keys in the result.

### TypeScript

Read `references/typescript.md` for vulnerable-vs-safe snippets.

Detect these sink categories:

- **Same JavaScript sinks apply**: Node.js runtime and browser state
  management patterns are vulnerable regardless of TypeScript typing.
- **Type-guarded parameters**: parameters typed as Partial objects offer no
  runtime protection against __proto__ injection.

### Python

Prototype pollution is not applicable to Python. Read `references/python.md`
for explanation. Python uses attribute dictionaries for object state, not
prototype chains. Assignment does not affect other instances.

### PHP

Prototype pollution is not applicable to PHP. Read `references/php.md` for
explanation. PHP does not have prototype chains; objects are instances of
classes with fixed property sets.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the sink call.
- `meta.code_snippet`: 2-6 lines of source containing the sink.
- `meta.reasoning`: one sentence explaining why the pattern is
  prototype pollution at this location.
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

Do not emit a finding when:

- The sink is guarded by input validation that explicitly filters
  `__proto__`, `constructor`, and `prototype` keys before the merge.
- The target is created with `Object.create(null)` (no prototype
  chain to pollute).
- The operation is shallow (e.g., object spread `{...obj}`) and does
  not recurse into nested values.

## Output payload skeleton

Emit one JSON object per finding with these fixed fields for
`injection.prototype_pollution`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing the sink, the source, and what an attacker can do>",
  "severity": "high",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-1321"],
  "finding_type": ["vulnerability"],
  "rule_id": "injection.prototype_pollution",
  "meta": {
    "title": "<short human title, e.g. 'Prototype pollution via request merge'>",
    "owasp_name": "Injection",
    "remediation": "<per-finding; see remediation guidance below>",
    "code_snippet": "<2-6 lines of source containing the sink>",
    "taint_source": "<request parameter or upstream variable, when traceable>",
    "reasoning": "<one sentence explaining the defect at this location>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for the
full field list and validator behavior.

## Remediation guidance for the scanner

Write `meta.remediation` inline based on the actual library
observed in the code. Use the safe patterns from the per-language
reference files to write specific, actionable remediation.

- Name the library and its specific safe API
- Show the exact placeholder style or query builder method
- Keep it two to four sentences

## Common false positives

- **Shallow merge operations**: `{...obj}`, `Object.assign({}, obj)`
  are safe; they create new objects and do not traverse prototypes.
- **Merge of constants or server-side-only data**: `_.merge(config,
  SERVER_DEFAULTS)` is safe if `SERVER_DEFAULTS` is a compile-time
  constant with no user reachability.
- **Input validation that filters dangerous keys**: `const safe =
  filterKeys(userInput, ['__proto__', 'constructor', 'prototype']);
  merge(target, safe);` is safe when `filterKeys` is implemented
  correctly.
- **Assignment to Object.create(null)**: `const target =
  Object.create(null); merge(target, userInput);` is safe because
  there is no prototype chain.
- **Type-guarded parameters in TypeScript**: A TypeScript parameter
  typed as `Partial<ConfigShape>` offers no runtime protection; the
  vulnerability remains.

## References

- `references/javascript.md`: Node.js and browser patterns for
  lodash, native merge operations, query parsing.
- `references/typescript.md`: TypeScript patterns for state
  management and typed parameters.
- `references/python.md`: Explanation of why prototype pollution
  does not apply.
- `references/php.md`: Explanation of why prototype pollution does
  not apply.
