---
name: tally-scan-injection-reflection
description: >
  Scan the target repo for unsafe reflection defects. Detects dynamic
  class/function/method instantiation and invocation on user-controlled
  values, method dispatch via getattr on request data, dynamic module
  loading from user input, and ReflectionClass instantiation from
  untrusted sources. Emits findings shaped for Tally MCP submission
  (rule_id `injection.reflection`, CWE-470, severity high). Invoke when
  the user says "unsafe reflection", "dynamic instantiation", "check for
  reflection attacks", or when dispatched by `tally-scan-external`.
---

# Tally scanner: Unsafe reflection

Detects sinks where user-controlled data reaches reflection or dynamic
invocation mechanisms without validation. Runs per-file in the target
repo (as dispatched by the `tally-scan-external` orchestrator, or
standalone when the user invokes this skill directly). Emits a JSON list
of findings; the orchestrator or the user submits them to Tally through
the `submit_finding` MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `injection.reflection` |
| Primary CWE | `CWE-470` |
| OWASP 2025 category | `Injection` |
| Default severity | `high` |
| Parent label (dedup) | `UnsafeReflection` |

Source: `docs/roadmap/TAL-148/taxonomy.md` T3 row 14.

## Detection matrix

### Python

- **getattr with user input**: method dispatch via `getattr(obj,
  user_input)()` where the attribute name is request-derived. Safe form
  validates against an allowlist.
- **Dynamic module loading**: `__import__(user_input)` or
  `importlib.import_module(user_input)` where the module name is
  request-sourced. Safe form uses an allowlist.
- **Dynamic function from globals/locals**: `globals()[user_input]()`
  or `locals()[user_input]()` with request data as the key. Safe form
  is an explicit dispatch table.
- **exec/eval on user data**: `exec(user_input)` or `eval(user_input)`
  with any request-derived value.

Defer to `references/python.md` for vulnerable-vs-safe snippets.

### PHP

- **Variable class instantiation**: `$class = $_GET['class']; new
  $class()` where the class name is request-derived. Safe form validates
  against an allowlist or uses a factory.
- **Variable function call**: `$func = $_GET['func']; $func()` with
  request data. Safe form is a dispatch array mapping allowed names to
  callable closures.
- **call_user_func with user input**: `call_user_func($userInput, ...)`
  where `$userInput` is request-sourced. Safe form is an allowlist.
- **ReflectionClass from user input**: `new ReflectionClass(
  $userInput)->newInstance(...)` with untrusted class name.

Defer to `references/php.md` for vulnerable-vs-safe snippets.

### JavaScript

- **Dynamic property access and invocation**: `obj[userInput]()`
  where the property name is request-derived. Safe form validates
  against an allowlist or uses Object.hasOwn before access.
- **Dynamic require/import**: `require(userInput)` or `import(
  userInput)` from request data. Safe form uses an allowlist.
- **global or window property access**: `global[userInput]()`
  or `window[userInput]()` with untrusted keys. Safe form is a
  dispatch object with fixed properties.

Defer to `references/javascript.md` for vulnerable-vs-safe snippets.

### TypeScript

- **Dynamic property access and invocation**: Same as JavaScript.
  TypeScript's type system does not prevent runtime dynamic property
  access from user input.
- **Dynamic require/import**: Same as JavaScript.
- **Type-unsafe casting**: TypeScript-specific patterns like `(obj as
  any)[userInput]()` that explicitly bypass type checking. Still
  vulnerable at runtime.

Defer to `references/typescript.md` for vulnerable-vs-safe snippets.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the sink call.
- `meta.code_snippet`: 2-6 lines of source containing the sink.
- `meta.reasoning`: one sentence explaining why the pattern is unsafe
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
`injection.reflection`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing the sink, the source, and what an
  attacker can do>",
  "severity": "high",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-470"],
  "finding_type": ["vulnerability"],
  "rule_id": "injection.reflection",
  "meta": {
    "title": "<short human title, e.g. 'Dynamic method dispatch on
    user input'>",
    "owasp_name": "Injection",
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
library or framework observed in the code. Examples of good
remediation strings:

- **Python getattr**: `Create a whitelist of allowed method names
  and check the attribute name against it before calling getattr.
  Example: if method_name in ALLOWED_METHODS: getattr(obj,
  method_name)().`
- **Python importlib**: `Maintain an allowlist of safe module names.
  Check the requested module name against the list before calling
  importlib.import_module(). Never import arbitrary modules from
  request data.`
- **PHP variable class**: `Build a registry of allowed classes and
  check the input against it. Example: if (in_array($class,
  ALLOWED_CLASSES)) { $obj = new $class(); }. Better, use a factory
  pattern that maps class names to callables.`
- **PHP call_user_func**: `Use a dispatch array mapping safe method
  names to closures or callables. Example: $handlers = ['method1' =>
  fn($x) => ..., ...]; if (isset($handlers[$name])) {
  $handlers[$name]($data); }`.
- **JavaScript dynamic property access**: `Build an allowlist of
  safe property names and use Object.hasOwn() to check before access.
  Example: if (ALLOWED_METHODS.includes(methodName)) {
  obj[methodName](...).`
- **Dynamic require/import**: `Use a dispatch map for code that
  chooses which module to load. Example: const modules = { 'module1':
  require('./module1'), 'module2': require('./module2') };
  const selected = modules[userInput];`.

Keep it two to four sentences. Vague guidance ("use an allowlist")
is worse than no guidance.

## Common false positives

- **Static-key property access**: `obj.method()` or `obj['method']()`
  where the key is a string literal, not a variable. No user input.
- **Validated property access**: `obj[userInput]()` where `userInput`
  is checked against an explicit allowlist before use.
- **Dispatch tables**: `ALLOWED_METHODS[userInput]()` where
  `ALLOWED_METHODS` is a constant or frozen mapping and the user input
  can only select from its keys.
- **Type-safe reflective access**: `getattr(obj, attr)` where `attr`
  is from a typed Enum or fixed configuration constant with no user
  reachability.
- **Private/internal methods**: Reflection on methods that are
  genuinely private and never exposed to an attacker (e.g., internal
  framework helpers). If the method is internal but the name is still
  user-controlled, it is not safe.

## References

- `references/python.md`: Python patterns for getattr, importlib,
  `__import__`, globals/locals, exec/eval.
- `references/php.md`: PHP patterns for variable class instantiation,
  call_user_func, ReflectionClass.
- `references/javascript.md`: Node patterns for dynamic property
  access, require, import().
- `references/typescript.md`: TypeScript patterns for dynamic property
  access, require, import(), type-unsafe casting.
