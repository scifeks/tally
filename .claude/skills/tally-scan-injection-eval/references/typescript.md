# TypeScript code injection patterns

Vulnerable-vs-safe snippets for the TypeScript eval, Function,
setTimeout/setInterval, and vm module functions the `injection.eval`
scanner recognizes. TypeScript does not prevent eval or Function
constructor calls at the type level; runtime behavior is identical
to JavaScript.

## eval() function

### Vulnerable

```typescript
const userCode: string = req.query.code as string;
eval(userCode);

const userData: string = req.body.json as string;
const result = eval(`(${userData})`);
```

### Safe

```typescript
interface UserData {
    name: string;
    age: number;
}
const userData = req.body.json as string;
const data: UserData = JSON.parse(userData);

const calculatedValue: number = 2 + 3;
```

`eval()` parses and executes arbitrary JavaScript code. Type
annotations do not prevent this at runtime. Use `JSON.parse()` with
type narrowing instead.

## Function() constructor

### Vulnerable

```typescript
const userCode: string = req.query.func as string;
const fn: Function = new Function(userCode);
fn();

type Operation = (a: number, b: number) => number;
const argsAndBody: string[] = req.body.code.split(',');
const dynamicFn: Operation = Function(...argsAndBody) as Operation;
```

### Safe

```typescript
interface Handlers {
    [key: string]: (a: number, b: number) => number;
}

const handlers: Handlers = {
    "add": (a: number, b: number): number => a + b,
    "multiply": (a: number, b: number): number => a * b,
};

const operation = req.query.op as string;
if (!(operation in handlers)) {
    throw new Error("Unknown operation");
}
const result = handlers[operation](5, 3);
```

The `Function()` constructor creates a function from a string at
runtime, bypassing TypeScript's type safety. Never pass user input
to it. Use a typed function dispatch table instead.

## setTimeout() and setInterval() with string

### Vulnerable

```typescript
const delayCode: string = req.query.action as string;
setTimeout(delayCode, 1000);

const command: string = req.body.command as string;
setInterval(command, 5000);
```

### Safe

```typescript
interface Actions {
    [key: string]: () => void;
}

const actions: Actions = {
    "refresh": (): void => location.reload(),
    "logout": (): void => logoutUser(),
};

const action = req.query.action as string;
if (!(action in actions)) {
    throw new Error("Unknown action");
}
setTimeout(actions[action], 1000);

setInterval((): void => {
    console.log("Periodic task");
}, 5000);
```

Passing a string to `setTimeout()` or `setInterval()` evaluates it as
code at runtime. Type annotations do not prevent this. Pass a function
reference instead.

## vm.runInNewContext()

### Vulnerable

```typescript
import vm from "vm";

const userScript: string = req.body.code as string;
vm.runInNewContext(userScript);

const expr: string = req.query.expr as string;
const result = vm.runInNewContext(expr);
```

### Safe

```typescript
import vm from "vm";

interface Sandbox {
    [key: string]: any;
}

const userScript: string = req.body.code as string;
const sandbox: Sandbox = {
    console: console,
    JSON: JSON,
};
vm.runInNewContext(userScript, sandbox);

const allowedOps: Sandbox = {
    safe_add: (a: number, b: number): number => a + b,
};
const expr = "safe_add(2, 3)";
const result = vm.runInNewContext(expr, allowedOps);
```

`vm.runInNewContext()` executes code in a new sandbox. Without a
restricted sandbox, this is equivalent to `eval()`. Constrain the
sandbox object to expose only safe functions and data.

## vm.runInThisContext()

### Vulnerable

```typescript
import vm from "vm";

const userCode: string = req.body.code as string;
vm.runInThisContext(userCode);
```

### Safe

```typescript
import vm from "vm";

const script: vm.Script = new vm.Script("2 + 3");
const result: number = script.runInThisContext() as number;
```

`vm.runInThisContext()` runs code in the current V8 context with
access to all globals. Never pass user input to it. Use
`vm.runInNewContext()` with a controlled sandbox if you need dynamic
code execution.

## Dynamic function dispatch (safe pattern)

When you need to call a method dynamically, use a typed dispatch table
with an explicit allowlist:

```typescript
interface UserHandlers {
    [key: string]: (id?: string) => Promise<any>;
}

const handlers: UserHandlers = {
    "getUserById": async (id: string): Promise<User> =>
        db.users.findById(id),
    "listUsers": async (): Promise<User[]> =>
        db.users.list(),
    "deleteUser": async (id: string): Promise<void> =>
        db.users.delete(id),
};

const action = req.query.action as string;
if (!(action in handlers)) {
    throw new Error(`Unknown action: ${action}`);
}

const result = await handlers[action](req.query.id);
```

The typed interface serves as both documentation and allowlist at
compile time. At runtime, only predefined handlers can be invoked.
