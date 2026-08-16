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

Source: `docs/roadmap/TAL-148/taxonomy.md` T3 row 28.

## Detection matrix

### JavaScript

- **Recursive merge with user input**: `_.merge(target, req.body)`,
  `$.extend(true, {}, req.query)`, or custom recursive merge functions
  that traverse and merge user-supplied objects without filtering
  `__proto__` or `constructor.prototype` keys.
- **Object.assign on shared object**: `Object.assign(sharedConfig,
  userInput)` where the target is a module-level or shared state
  object reachable by multiple request handlers.
- **Deep clone with prototype traversal**: Libraries or custom code
  that use `JSON.parse` on user input and recursively merge the
  result into an existing object.
- **Query string parsing**: `qs.parse(queryString, {allowPrototypes:
  true})` or equivalent parsers that allow `__proto__`, `constructor`,
  or `prototype` keys in the parsed result.
- **lodash merge variants**: `_.merge()`, `_.set()`, `_.defaultsDeep()`
  with user input without prototype filtering.

Defer to `references/javascript.md` for vulnerable-vs-safe snippets.

### TypeScript

- Same JavaScript sinks apply on the Node.js runtime and in
  browser-shared state management (e.g., Vuex, Redux stores
  initialized from user data).
- **Type-unsafety in recursion**: TypeScript type guards do not
  protect against `__proto__` injection; a parameter typed as
  `Partial<Config>` can still carry a `__proto__` key.

Defer to `references/typescript.md` for vulnerable-vs-safe snippets.

### Python

Prototype pollution is not applicable to Python. Python uses
attribute dictionaries (`__dict__`) for object state, not prototype
chains. Assignment to `__dict__` keys does not affect other object
instances. Refer to `references/python.md` for explanation.

### PHP

Prototype pollution is not applicable to PHP. PHP does not have
prototype chains; objects are instances of classes with fixed
property sets. Refer to `references/php.md` for explanation.

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
    "remediation": "<per-finding, per D19; see remediation guidance below>",
    "code_snippet": "<2-6 lines of source containing the sink>",
    "taint_source": "<request parameter or upstream variable, when traceable>",
    "reasoning": "<one sentence explaining the defect at this location>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for the
full field list and validator behavior.

## Remediation guidance for the scanner

Write `meta.remediation` inline based on the actual library observed in
the code. Examples of good remediation strings:

- **lodash (v4.17.21+)**: `The installed version of lodash has
  prototype pollution protection. Upgrade to the latest release if
  you are below 4.17.21. If upgrading is not an option, add an
  input-validation guard that rejects any key matching __proto__,
  constructor, or prototype before the merge.`
- **Custom merge function**: `Filter the input object before merging:
  filter out any keys equal to __proto__, constructor, or prototype.
  Create the target with Object.create(null) to disable the
  prototype chain entirely, or use a shallow copy (const result =
  {...existing, ...filtered};) instead of recursive merge.`
- **Object.assign on shared state**: `Avoid mutating shared
  module-level state with user input. Create a new object per
  request: const config = Object.assign({}, defaults, userInput);.
  Better, validate userInput and only assign known-safe keys.`
- **Query parsing**: `Use a query parser that disables prototype
  pollution: qs.parse(qs, {allowPrototypes: false}). Or validate
  after parsing to remove __proto__ and constructor keys.`

Keep it two to four sentences. Vague guidance ("filter user input")
is worse than no guidance.

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
