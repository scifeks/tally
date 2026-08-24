# JavaScript unsafe reflection patterns

Vulnerable-vs-safe snippets for the JavaScript reflection and dynamic
invocation mechanisms the `injection.reflection` scanner recognizes.
When multiple safe forms exist, the canonical one is shown first.

## Dynamic property access and invocation

### Vulnerable

```javascript
const method = req.query.method;
const result = obj[method]();

const action = req.body.action;
handlers[action](data);

const handler = req.params.handler;
api[handler]();
```

### Safe

```javascript
const ALLOWED_METHODS = new Set(['create', 'update', 'delete']);
const method = req.query.method;
if (!ALLOWED_METHODS.has(method)) {
    throw new Error('Method not allowed');
}
const result = obj[method]();
```

Validate the property name against an explicit allowlist before
access. Use `Set` for O(1) lookups or `Object.hasOwn()` to verify
existence.

## Safe dispatch object pattern

### Vulnerable

```javascript
const route = req.path.split('/')[1];
const handler = handlers[route];
handler(req, res);
```

### Safe

```javascript
const handlers = {
    users: handleUsers,
    products: handleProducts,
    orders: handleOrders,
};

const route = req.path.split('/')[1];
const handler = handlers[route];
if (!handler) {
    return res.status(404).json({ error: 'Not found' });
}
handler(req, res);
```

Build a fixed dispatch object with only safe handler functions.
Check if the handler exists before calling.

## Dynamic require

### Vulnerable

```javascript
const moduleName = req.query.plugin;
const module = require(moduleName);

const lib = req.body.library;
const handler = require(`./plugins/${lib}`);
```

### Safe

```javascript
const ALLOWED_MODULES = {
    auth: require('./plugins/auth'),
    billing: require('./plugins/billing'),
    notifications: require('./plugins/notifications'),
};

const moduleName = req.query.plugin;
const module = ALLOWED_MODULES[moduleName];
if (!module) {
    throw new Error('Plugin not found');
}
```

Never use template literals or string concatenation with user input
in require(). Load all possible modules upfront and select from a
dispatch object.

## Dynamic import

### Vulnerable

```javascript
const modulePath = req.query.path;
import(modulePath).then(module => {
    module.handle();
});

const plugin = req.body.plugin;
const loaded = import(`./plugins/${plugin}`);
```

### Safe

```javascript
const PLUGINS = {
    auth: () => import('./plugins/auth'),
    logs: () => import('./plugins/logs'),
};

const plugin = req.body.plugin;
const loader = PLUGINS[plugin];
if (!loader) {
    throw new Error('Plugin not found');
}
const module = await loader();
```

Use a dispatch map of lazy-loaded modules. Import all possible
modules through controlled paths.

## Safe Express routing pattern

### Vulnerable

```javascript
app.get('/:action', (req, res) => {
    const action = req.params.action;
    api[action](req, res);
});
```

### Safe

```javascript
app.get('/create', (req, res) => {
    handleCreate(req, res);
});

app.get('/delete', (req, res) => {
    handleDelete(req, res);
});

app.get('/update', (req, res) => {
    handleUpdate(req, res);
});
```

Define explicit routes for each action instead of parameterizing the
handler name.

## Safe property access with allowlist

### Vulnerable

```javascript
const prop = request.body.property;
const value = obj[prop];
console.log(value);
```

### Safe

```javascript
const ALLOWED_PROPS = ['name', 'email', 'phone'];
const prop = request.body.property;
if (!ALLOWED_PROPS.includes(prop)) {
    throw new Error('Property access denied');
}
const value = obj[prop];
```

Even for read-only property access, validate against an allowlist if
the property name comes from user input.

## Safe switch statement pattern

### Vulnerable

```javascript
const operation = req.query.op;
const fn = operations[operation];
fn(a, b);
```

### Safe

```javascript
const operation = req.query.op;
let result;
switch (operation) {
    case 'add':
        result = add(a, b);
        break;
    case 'subtract':
        result = subtract(a, b);
        break;
    case 'multiply':
        result = multiply(a, b);
        break;
    default:
        throw new Error('Unknown operation');
}
```

A switch statement makes the allowed operations explicit and
exhaustive at compile time.
