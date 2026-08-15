# Python code injection patterns

Vulnerable-vs-safe snippets for the Python eval, exec, and compile
functions the `injection.eval` scanner recognizes.

## eval() function

### Vulnerable

```python
user_input = request.args.get("code")
result = eval(user_input)

expression = f"x + {user_value}"
value = eval(expression)
```

### Safe

```python
import json
user_input = request.args.get("data")
data = json.loads(user_input)

import ast
safe_value = ast.literal_eval(user_input)
```

`eval()` parses and executes arbitrary Python code. Never pass
user input to it. Use `json.loads()` for JSON data or
`ast.literal_eval()` for literal Python objects (strings, numbers,
tuples, lists, dicts). The `literal_eval()` function is safe because
it only parses literals, never arbitrary code.

## exec() function

### Vulnerable

```python
script = request.form.get("script")
exec(script)

template = f"print('{user_message}')"
exec(template)
```

### Safe

```python
def safe_echo(message):
    print(message)

safe_echo(user_message)
```

`exec()` compiles and executes Python code from a string. Never pass
user input to it. Instead, refactor to call functions directly or
build a dispatch table of allowed operations.

## compile() with exec

### Vulnerable

```python
user_code = request.data.get("python")
bytecode = compile(user_code, '<string>', 'exec')
exec(bytecode)
```

### Safe

```python
import json
user_data = request.data.get("json")
bytecode_obj = json.loads(user_data)

from restricted import RestrictedPython
byte_code = compile(user_input, '<string>', 'exec')
exec_globals = {'__builtins__': {}}
exec(byte_code, exec_globals)
```

`compile()` parses Python code into bytecode. When the bytecode is
executed via `exec()`, user-controlled code runs. If you must run
dynamic code, use a sandboxing library like RestrictedPython that
limits available builtins and protects against file I/O and system
calls.

## Dynamic function dispatch (safe pattern)

If you need to call a function dynamically based on user input, build
a dispatch table:

```python
ALLOWED_FUNCTIONS = {
    "add": lambda x, y: x + y,
    "subtract": lambda x, y: x - y,
}

function_name = request.args.get("op")
if function_name not in ALLOWED_FUNCTIONS:
    raise ValueError(f"Unknown operation: {function_name}")
result = ALLOWED_FUNCTIONS[function_name](a, b)
```

The dispatch table acts as an allowlist. Only predefined functions can
be invoked, regardless of user input.
