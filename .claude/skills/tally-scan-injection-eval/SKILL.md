---
name: tally-scan-injection-eval
description: >
  Scan the target repo for code injection defects via eval, exec, and
  compile functions. Detects eval() and exec() calls with user input,
  Function constructors receiving user-controlled strings, and unsafe
  template evaluation. Emits findings shaped for Tally MCP submission
  (rule_id `injection.eval`, CWE-95, severity critical). Invoke when
  the user says "code injection", "eval injection", "check for eval",
  or when dispatched by `tally-scan-external`.
---

# Tally scanner: Code injection (eval/exec)

Detects sinks where user-controlled data reaches a code interpreter
(eval, exec, compile, Function constructor, or equivalent dynamic code
evaluation) without sanitization. Runs per-file in the target repo (as
dispatched by the `tally-scan-external` orchestrator, or standalone
when the user invokes this skill directly). Emits a JSON list of
findings; the orchestrator or the user submits them to Tally through
the `submit_finding` MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `injection.eval` |
| Primary CWE | `CWE-95` |
| Secondary CWE | `CWE-94` |
| OWASP 2025 category | `Injection` |
| Default severity | `critical` |
| Parent label (dedup) | `CodeInjection` |


## Detection matrix

### Python

- **`eval()` call**: `eval(<user_input>)` or `eval(f-string
  containing user data)`. The `eval()` function parses and executes
  Python code directly.
- **`exec()` call**: `exec(<user_input>)` or `exec(f-string
  containing user data)`. The `exec()` function executes Python code.
- **`compile()` with exec**: `code = compile(<user_input>, ...) ;
  exec(code)`. The `compile()` function parses code; when the compiled
  object is executed, injected code runs.
- **`pickle.loads()` note**: Deserialization is code execution but
  belongs to a separate deserialization skill; flag only eval/exec/
  compile here.

Read `references/python.md` for vulnerable-vs-safe code patterns.

### PHP

- **`eval()` call**: `eval($userInput)` executes a string as PHP code.
- **`assert()` call**: In PHP < 8.0 or when `assert.active=1`,
  `assert($userInput)` executes the string as code (assertion syntax).
  PHP 8.0+ treats assertions as a language construct but can still
  execute code if older configurations persist.
- **`create_function()`**: `create_function('$x', $userInput)` is
  deprecated but dangerous. It compiles the second argument as PHP
  code. Removed in PHP 8+.
- **`preg_replace()` with /e flag**: `preg_replace('/.*/e',
  $userInput, ...)` evaluates the replacement as PHP code. The `/e`
  flag was removed in PHP 7; legacy codebases may still use it.

Read `references/php.md` for vulnerable-vs-safe code patterns.

### JavaScript

- **`eval()` call**: `eval(userInput)` parses and executes a string as
  JavaScript code.
- **`Function()` constructor**: `new Function(userInput)` or
  `Function(userInput)` constructs a function from a string argument.
- **`setTimeout()` and `setInterval()` with string**: `setTimeout(
  userInput, ms)` where the first argument is a string (not a function
  reference) causes the string to be evaluated as code. Same for
  `setInterval()`.
- **`vm.runInNewContext()` and `vm.runInThisContext()`**: `vm.
  runInNewContext(userInput)` and `vm.runInThisContext(userInput)`
  evaluate user-controlled strings as code in a new or current VM
  context, respectively.

Read `references/javascript.md` for vulnerable-vs-safe code patterns.

### TypeScript

- **`eval()` call**: TypeScript does not prevent `eval()` at the type
  level; same as JavaScript.
- **`Function()` constructor**: Same as JavaScript.
- **`setTimeout()` and `setInterval()`**: Same as JavaScript; dynamic
  string evaluation is possible despite type annotations.
- **`vm.runInNewContext()` and `vm.runInThisContext()`**: Same as
  JavaScript.

Read `references/typescript.md` for vulnerable-vs-safe code patterns.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the sink call.
- `meta.code_snippet`: 2-6 lines of source containing the sink.
- `meta.reasoning`: one sentence explaining why the pattern is a code
  injection at this location.
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
`injection.eval`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing the sink, the source, and what an
attacker can do>",
  "severity": "critical",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-95", "CWE-94"],
  "finding_type": ["vulnerability"],
  "rule_id": "injection.eval",
  "meta": {
    "title": "<short human title, e.g. 'Code injection via eval()'>",
    "owasp_name": "Injection",
    "remediation": "<per-finding; see remediation guidance below>",
    "code_snippet": "<2-6 lines of source containing the sink>",
    "taint_source": "<request parameter or upstream variable, when
traceable>",
    "reasoning": "<one sentence explaining the defect at this location>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for
the full field list and validator behavior.

## Remediation guidance for the scanner

Write `meta.remediation` inline based on the actual library or framework
observed in the code. Examples of good remediation strings:

- **Python eval/exec removal**: `Remove the eval() or exec() call
  entirely. If the intent is to evaluate a JSON or YAML literal,
  use json.loads() or yaml.safe_load() instead. If you need to run
  dynamically discovered functions, build a dispatch table mapping
  function names to callable references and use a dictionary lookup.`
- **Python compile + exec**: `Avoid compile() and exec() for
  user-controlled input. If you need dynamic computation, refactor
  to a sandbox library like RestrictedPython that controls the code
  environment, or use json.loads() for structured data.`
- **JavaScript eval removal**: `Remove the eval() call. If
  deserializing JSON, use JSON.parse() instead. If building a
  dynamic expression, pass a function reference to setTimeout(),
  not a string.`
- **JavaScript Function constructor**: `Avoid the Function()
  constructor with user input. Pass a function reference, not a
  string. For JSON, use JSON.parse().`
- **JavaScript setTimeout/setInterval string form**: `Pass a
  function reference instead of a string: setTimeout(myFunction,
  ms), not setTimeout(userString, ms).`
- **PHP eval removal**: `Avoid eval() entirely. If you must run
  user-controlled code, use a whitelist of allowed functions and
  validate inputs against it. For dynamic function dispatch, build
  a switch statement or associative array mapping allowed names to
  closures.`
- **PHP assert() safety**: `In PHP < 8.0, ensure assert.active=0
  in production (it is the default). In PHP 8.0+, assert() is a
  language construct and is safe, but audit the rest of the code
  for legacy eval() patterns.`

Keep it two to four sentences. Vague guidance ("avoid eval") is
worse than no guidance.

## Common false positives

- **Compile-time constants**: `eval('123 + 456')` is safe if the
  string is a literal. Confirm the string is not later reassigned
  or populated from a request.
- **`ast.literal_eval()` (Python)**: This function is safe by
  design. It only parses literals (strings, numbers, tuples, lists,
  dicts), never code. Do not flag it.
- **`JSON.parse()` (JavaScript)**: JSON parsing is not code
  execution. Do not flag it.
- **Function references (JavaScript)**: `setTimeout(myFunction, ms)`
  where `myFunction` is a function reference (not a string) is safe.
  The string form is dangerous.
- **Static code generation**: If code is generated at build time
  from a template with no user input, and the generated file is
  checked into version control, the result is safe (though unusual).
- **Sandboxed execution**: Some libraries (RestrictedPython,
  PyRestrictedPython, VM2 for Node) provide isolated execution
  contexts with constrained builtins. When user code runs in a
  well-configured sandbox that forbids file I/O and system calls,
  the risk is lower. Still flag the finding but note the sandboxing
  in remediation.

## References

- `references/python.md`: Python patterns for eval, exec, compile,
  and safe alternatives.
- `references/php.md`: PHP patterns for eval, assert, create_function,
  and preg_replace /e.
- `references/javascript.md`: JavaScript patterns for eval,
  Function, setTimeout/setInterval, and vm module.
- `references/typescript.md`: TypeScript patterns (same as JavaScript
  at runtime).
