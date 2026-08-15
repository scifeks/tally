---
name: tally-scan-data-integrity-insecure-deserialization
description: >
  Scan the target repo for insecure deserialization defects. Detects
  unsafe deserializers (pickle, yaml.load, unserialize, node-serialize)
  called on data reachable from user input, HTTP requests, uploaded files,
  or database fields sourced from untrusted sources. Emits findings shaped
  for Tally MCP submission (rule_id `data_integrity.insecure_deserialization`,
  CWE-502, severity critical). Invoke when the user says "insecure
  deserialization", "pickle vulnerability", "unserialize vulnerability",
  "deserialization attack", or when dispatched by `tally-scan-external`.
---

# Tally scanner: insecure deserialization

Detects sinks where untrusted data is deserialized by a deserializer that
allows arbitrary code execution or object instantiation. Runs per-file in
the target repo (as dispatched by the `tally-scan-external` orchestrator,
or standalone when the user invokes this skill directly). Emits a JSON list
of findings; the orchestrator or the user submits them to Tally through the
`submit_finding` MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `data_integrity.insecure_deserialization` |
| Primary CWE | `CWE-502` |
| OWASP 2025 category | `Software or Data Integrity Failures` |
| Default severity | `critical` |
| Parent label (dedup) | `InsecureDeserialization` |

Source: `docs/roadmap/TAL-148/taxonomy.md` T3 row 8.

## Detection matrix

### Python

- **pickle.loads() / pickle.load()**: deserialization on data reachable
  from HTTP request, uploaded file, database field with no server-side
  serialization origin, Redis/Memcached entry keyed by user input, or
  network socket. pickle bytecode can execute arbitrary Python; never use
  on untrusted data.
- **yaml.load()**: unsafe YAML deserialization when `Loader` is not
  specified, is not `SafeLoader` (or `yaml.safe_load()` not used). Allows
  Python object constructor tags that execute code.
- **marshal.loads()**: deserialization of untrusted marshaled Python
  objects. Less common than pickle but equally unsafe.
- **shelve.open()**: file path is user-supplied or influenced by request
  data. Shelve opens a persistent dictionary backed by pickle.
- **jsonpickle.decode()**: deserialization without strict mode, accepting
  arbitrary Python object serialization in JSON form.
- **dill.loads()**: unsafe alternative to pickle; allows lambda and code
  object serialization.

Defer to `references/python.md` for vulnerable-vs-safe snippets.

### PHP

- **unserialize()**: deserialization of user-controlled data (request
  parameter, cookie, database field sourced from user input, uploaded
  file). Triggers `__wakeup`, `__destruct`, and `__toString` magic methods
  on instantiated objects; gadget chains can lead to code execution or
  file operations.
- **unserialize() without options**: called without the second argument
  `['allowed_classes' => false]` or without an explicit allowlist. Without
  the option, any class can be instantiated.
- **Object injection via crafted payload**: a serialized payload containing
  one or more objects designed to chain magic method calls and reach a code
  execution or file operation sink.

Defer to `references/php.md` for vulnerable-vs-safe snippets.

### JavaScript

- **node-serialize unserialize()**: library allows IIFE (Immediately
  Invoked Function Expression) and code evaluation. Crafted payloads can
  execute arbitrary JavaScript.
- **serialize-to-js unserialize()**: similar to node-serialize; unsafe
  against untrusted input.
- **js-yaml.load()** (pre-v4) with default schema: accepts `!!js/function`
  tags that construct function objects, which can execute code. In v4+,
  the unsafe behavior was removed; `load()` is now safe by default unless
  schema is explicitly set to an unsafe value.
- **cryo.parse()**: deserialization library that allows function objects;
  crafted payloads can achieve code execution.
- **eval() of JSON-like data**: use of `eval()` on JSON or JSON-like
  strings instead of `JSON.parse()`.

Defer to `references/javascript.md` for vulnerable-vs-safe snippets.

### TypeScript

- **js-yaml.load()**: same as JavaScript; check the schema parameter.
- **class-transformer plainToInstance()**: when `enableImplicitConversion`
  is true and the DTO has gadget classes (e.g., classes with `@Type()`
  decorators that instantiate dangerous constructors), untrusted input can
  trigger object instantiation with attacker-controlled property values.
- **Uncontrolled object instantiation**: TypeScript wrappers around unsafe
  deserializers; run the JavaScript detection checks on the underlying
  runtime behavior.

Defer to `references/typescript.md` for vulnerable-vs-safe snippets.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the sink call.
- `meta.code_snippet`: 2-6 lines of source containing the sink.
- `meta.reasoning`: one sentence explaining why the pattern is a
  deserialization vulnerability at this location.
- When the taint source is in the same file:
  `meta.taint_source` naming the request parameter, uploaded file, or
  upstream variable that reaches the sink.

Set `confidence`:

- `confirmed` when a taint source is traced from an HTTP request handler,
  uploaded file, or database field to the sink in the same file.
- `probable` when the sink pattern matches and the argument is clearly a
  variable (not a constant), but the source is inferred or in an adjacent
  function.
- `potential` when the sink is suspicious but the data origin is unclear.

## Output payload skeleton

Emit one JSON object per finding with these fixed fields for
`data_integrity.insecure_deserialization`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing the sink, the source, and what an attacker can do>",
  "severity": "critical",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-502"],
  "finding_type": ["vulnerability"],
  "rule_id": "data_integrity.insecure_deserialization",
  "meta": {
    "title": "<short human title, e.g. 'Insecure deserialization via pickle'>",
    "owasp_name": "Software or Data Integrity Failures",
    "remediation": "<per-finding, per D19; see remediation guidance below>",
    "code_snippet": "<2-6 lines of source containing the sink>",
    "taint_source": "<request parameter or upstream variable, when traceable>",
    "reasoning": "<one sentence explaining the defect at this location>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for the full
field list and validator behavior.

## Remediation guidance for the scanner

Per D19, write `meta.remediation` inline based on the actual library
observed in the code. Examples of good remediation strings:

- **Python pickle**: `Replace pickle with JSON for data exchange or
  storage. pickle bytecode allows arbitrary code execution; there is no
  safe way to deserialize untrusted pickle payloads. If pickle is required
  for internal caching, sign the serialized data with HMAC before storing
  and verify the signature before deserializing.`
- **Python yaml**: `Replace yaml.load() with yaml.safe_load(). SafeLoader
  rejects Python object constructor tags and only deserializes primitive
  types and standard containers.`
- **PHP unserialize**: `Add the second argument
  ['allowed_classes' => false] to unserialize() to prevent object
  instantiation. Better, switch to json_decode() for data exchange and
  store serialized data only internally.`
- **node-serialize**: `Replace node-serialize with JSON.stringify() and
  JSON.parse(). The node-serialize package allows IIFE execution through
  crafted payloads and is fundamentally unsafe for untrusted input.`
- **js-yaml (v3)**: `Upgrade js-yaml to v4 or later, or explicitly set
  schema: yaml.SAFE_SCHEMA in the load() call. v4+ made SafeSchema the
  default and removed js/function tag support.`

Keep it two to four sentences. Vague guidance ("do not deserialize
untrusted data") is worse than no guidance.

## Common false positives

- **Deserialization of data the application itself serialized**: pickle
  or marshal used on data read from a file the application wrote in the
  same session or a prior trusted session, with no external write path.
- **yaml.load() on config files**: YAML configuration files shipped with
  the application or in restricted system directories (not user-supplied).
- **JSON.parse()**: safe; no code execution vector.
- **unserialize() with allowed_classes false**: PHP unserialize() called
  with `['allowed_classes' => false]` is safe; prevents object
  instantiation.
- **Safe YAML deserializers**: yaml.safe_load() (Python), yaml.SAFE_SCHEMA
  (JavaScript v3), js-yaml v4+ with default schema.
- **Deserialization of primitive types**: pickle or marshal used only on
  strings, integers, or lists with no custom objects; unlikely to be
  exploitable unless the data contains embedded code objects.

## References

- `references/python.md`: Python patterns for pickle, yaml, marshal,
  shelve, jsonpickle, dill.
- `references/php.md`: PHP patterns for native unserialize, Laravel
  serialized sessions/cookies, object injection.
- `references/javascript.md`: Node patterns for node-serialize,
  serialize-to-js, js-yaml, cryo.
- `references/typescript.md`: TypeScript patterns for js-yaml, class-transformer.
