# JavaScript code injection patterns

Vulnerable-vs-safe snippets for the JavaScript eval, Function,
setTimeout/setInterval, and vm module functions the `injection.eval`
scanner recognizes.

## eval() function

### Vulnerable

```javascript
const userCode = req.query.code;
eval(userCode);

const userData = req.body.json;
const result = eval(`(${userData})`);
```

### Safe

```javascript
const userData = req.body.json;
const data = JSON.parse(userData);

const calculatedValue = 2 + 3;
const result = calculatedValue;
```

`eval()` parses and executes arbitrary JavaScript code. Never pass
user input to it. Use `JSON.parse()` for JSON data or compute values
directly without string evaluation.

## Function() constructor

### Vulnerable

```javascript
const userCode = req.query.func;
const fn = new Function(userCode);
fn();

const argsAndBody = req.body.code;
const dynamicFn = Function(...argsAndBody.split(','));
dynamicFn();
```

### Safe

```javascript
const myFunctions = {
    "add": (a, b) => a + b,
    "multiply": (a, b) => a * b,
};

const operation = req.query.op;
if (!Object.hasOwn(myFunctions, operation)) {
    throw new Error("Unknown operation");
}
const result = myFunctions[operation](5, 3);
```

The `Function()` constructor creates a function from a string. Never
pass user input to it. Use a function dispatch table with an allowlist
instead.

## setTimeout() and setInterval() with string

### Vulnerable

```javascript
const delayCode = req.query.action;
setTimeout(delayCode, 1000);

const interval = req.body.interval;
setInterval(userCommand, interval);
```

### Safe

```javascript
const myActions = {
    "refresh": () => location.reload(),
    "logout": () => logoutUser(),
};

const action = req.query.action;
if (!Object.hasOwn(myActions, action)) {
    throw new Error("Unknown action");
}
setTimeout(myActions[action], 1000);

setInterval(() => {
    console.log("Periodic task");
}, 5000);
```

When `setTimeout()` or `setInterval()` receive a string as the first
argument, the string is evaluated as code. Pass a function reference
instead. Use an allowlist if you need dynamic dispatch.

## vm.runInNewContext()

### Vulnerable

```javascript
const vm = require("vm");
const userScript = req.body.code;
vm.runInNewContext(userScript);

const expr = req.query.expr;
const result = vm.runInNewContext(expr);
```

### Safe

```javascript
const vm = require("vm");
const userScript = req.body.code;
const sandbox = {
    console: console,
    JSON: JSON,
};
vm.runInNewContext(userScript, sandbox);

const allowedContext = {
    safe_add: (a, b) => a + b,
};
const expr = "safe_add(2, 3)";
const result = vm.runInNewContext(expr, allowedContext);
```

`vm.runInNewContext()` executes a string in a new sandbox context.
If user input reaches the code, it executes as JavaScript. Restrict
the sandbox context to allow only safe functions and data. Use an
allowlist of approved operations.

## vm.runInThisContext()

### Vulnerable

```javascript
const vm = require("vm");
const userCode = req.body.code;
vm.runInThisContext(userCode);
```

### Safe

```javascript
const vm = require("vm");
const script = new vm.Script("2 + 3");
const result = script.runInThisContext();
```

`vm.runInThisContext()` executes code in the current V8 context and
has access to all global scope. Never pass user input to it. If
sandboxing is needed, use `vm.runInNewContext()` with a controlled
sandbox instead.

## Dynamic function dispatch (safe pattern)

When you need to call a function dynamically based on user input, build
a dispatch object with an allowlist:

```javascript
const handlers = {
    "getUserById": (id) => db.users.find(id),
    "listUsers": () => db.users.list(),
    "deleteUser": (id) => db.users.delete(id),
};

const action = req.query.action;
if (!Object.hasOwn(handlers, action)) {
    throw new Error(`Unknown action: ${action}`);
}

const result = handlers[action](req.query.id);
```

The dispatch object acts as an allowlist. Only predefined functions
can be invoked, regardless of user input.
