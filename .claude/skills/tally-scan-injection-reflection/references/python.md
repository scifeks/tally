# Python unsafe reflection patterns

Vulnerable-vs-safe snippets for the Python reflection and dynamic
invocation mechanisms the `injection.reflection` scanner recognizes.
When multiple safe forms exist, the canonical one is shown first.

## getattr with dynamic attribute names

### Vulnerable

```python
user_method = request.args.get("method")
result = getattr(user_obj, user_method)()

action = request.form.get("action")
handler = getattr(self, action)
handler()
```

### Safe

```python
ALLOWED_METHODS = {"create", "update", "delete"}
user_method = request.args.get("method")
if user_method in ALLOWED_METHODS:
    result = getattr(user_obj, user_method)()
else:
    raise ValueError(f"Unknown method: {user_method}")
```

Maintain an explicit set of allowed method names. Check the requested
method against the set before calling getattr.

## Dynamic module loading with importlib

### Vulnerable

```python
module_name = request.args.get("module")
module = importlib.import_module(module_name)
obj = module.Handler()

plugin_name = request.form.get("plugin")
plugin = __import__(plugin_name)
```

### Safe

```python
ALLOWED_MODULES = {"handlers.auth", "handlers.billing"}
module_name = request.args.get("module")
if module_name in ALLOWED_MODULES:
    module = importlib.import_module(module_name)
else:
    raise ValueError(f"Module not allowed: {module_name}")
```

Never call `importlib.import_module()` or `__import__()` on
untrusted input. Use an allowlist of safe module names.

## Dynamic function from globals

### Vulnerable

```python
func_name = request.query.get("func")
func = globals()[func_name]
result = func()

handler_name = request.json.get("handler")
handler = locals()[handler_name]
```

### Safe

```python
HANDLERS = {
    "login": handle_login,
    "logout": handle_logout,
    "register": handle_register,
}
func_name = request.query.get("func")
if func_name in HANDLERS:
    result = HANDLERS[func_name]()
else:
    raise ValueError(f"Handler not found: {func_name}")
```

Use an explicit dispatch dictionary instead of globals or locals.
This pattern is faster, clearer, and safe by design.

## exec and eval

### Vulnerable

```python
code = request.args.get("expression")
result = eval(code)

template = request.form.get("script")
exec(template)
```

### Safe

```python
# Avoid eval and exec entirely. Use a DSL or expression parser.
# For user-supplied expressions, use a safe parser library.
from simpleeval import simple_eval

expr = request.args.get("expression")
result = simple_eval(expr, names={"x": 10})
```

Avoid `eval()` and `exec()` on user input. If dynamic code execution
is needed, use a restricted language like `simpleeval`, `asteval`, or
a purpose-built DSL parser.

## Safe getattr pattern in Django

### Vulnerable

```python
class UserView:
    def dispatch(self, request, action):
        handler = getattr(self, action)
        return handler(request)
```

### Safe

```python
from django.views.generic import View

class UserView(View):
    def get(self, request):
        return self.handle_get(request)

    def post(self, request):
        return self.handle_post(request)

    http_method_names = ["get", "post"]
```

Use Django's built-in routing and method dispatch. Avoid parameterizing
the method name from request data.

## Safe getattr pattern with type hints

### Vulnerable

```python
operation = request.args.get("op")
calculator = Calculator()
result = getattr(calculator, operation)()
```

### Safe

```python
from typing import Callable, get_type_hints
from dataclasses import dataclass

@dataclass
class Operations:
    add: Callable
    subtract: Callable
    multiply: Callable

operations = Operations(
    add=lambda x, y: x + y,
    subtract=lambda x, y: x - y,
    multiply=lambda x, y: x * y,
)

op = request.args.get("op")
if op in ("add", "subtract", "multiply"):
    result = getattr(operations, op)()
```

Combine an allowlist check with an explicit object that holds only
safe callables.
