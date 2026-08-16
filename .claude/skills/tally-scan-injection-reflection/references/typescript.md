# TypeScript unsafe reflection patterns

Vulnerable-vs-safe snippets for the TypeScript reflection and dynamic
invocation mechanisms the `injection.reflection` scanner recognizes.
TypeScript's type system does not prevent runtime dynamic property
access or invocation from user input.

When multiple safe forms exist, the canonical one is shown first.

## Dynamic property access and invocation

### Vulnerable

```typescript
const method = req.query.method as string;
const result = (obj as any)[method]();

interface Handler {
    [key: string]: (data: any) => Promise<void>;
}
const handler = req.body.action as keyof Handler;
handlers[handler](data);
```

### Safe

```typescript
const ALLOWED_METHODS = new Set(['create', 'update', 'delete']);
const method = req.query.method;
if (!ALLOWED_METHODS.has(method)) {
    throw new Error('Method not allowed');
}
const result = (obj as Record<string, Function>)[method]();
```

Use an allowlist and type-safe dictionary access. Avoid `as any`
casts that bypass type checking.

## Safe typed dispatch object

### Vulnerable

```typescript
type Handler = (req: Request, res: Response) => Promise<void>;
type Handlers = Record<string, Handler>;

const handlers: Handlers = {
    users: handleUsers,
    products: handleProducts,
};

const route = (req.path.split('/')[1]) as keyof Handlers;
handlers[route](req, res);
```

### Safe

```typescript
type HandlerName = 'users' | 'products' | 'orders';

const handlers: Record<HandlerName, Handler> = {
    users: handleUsers,
    products: handleProducts,
    orders: handleOrders,
};

function getHandler(name: string): Handler | null {
    if (name === 'users' || name === 'products' || name === 'orders') {
        return handlers[name as HandlerName];
    }
    return null;
}

const route = req.path.split('/')[1];
const handler = getHandler(route);
if (!handler) {
    return res.status(404).json({ error: 'Not found' });
}
await handler(req, res);
```

Use a union type for allowed handler names. Validate against the type
before access.

## Dynamic require with CommonJS

### Vulnerable

```typescript
const moduleName = req.query.plugin as string;
const plugin = require(moduleName);

const lib = req.body.library;
import(lib).then(module => {
    module.run();
});
```

### Safe

```typescript
type PluginName = 'auth' | 'billing';

const plugins: Record<PluginName, any> = {
    auth: require('./plugins/auth'),
    billing: require('./plugins/billing'),
};

function getPlugin(name: string): any | null {
    if (name === 'auth' || name === 'billing') {
        return plugins[name as PluginName];
    }
    return null;
}

const plugin = getPlugin(req.query.plugin as string);
if (!plugin) {
    throw new Error('Plugin not found');
}
```

Load all possible modules upfront into a typed dispatch object.

## Dynamic import with async

### Vulnerable

```typescript
const modulePath = req.query.path as string;
const module = await import(modulePath);

const plugin: string = req.body.plugin;
const loaded = await import(`./handlers/${plugin}`);
loaded.execute();
```

### Safe

```typescript
type PluginLoader = () => Promise<PluginModule>;

const pluginLoaders: Record<string, PluginLoader> = {
    auth: () => import('./plugins/auth'),
    cache: () => import('./plugins/cache'),
    db: () => import('./plugins/db'),
};

async function loadPlugin(name: string): Promise<PluginModule> {
    const loader = pluginLoaders[name];
    if (!loader) {
        throw new Error('Plugin not found');
    }
    return loader();
}

const plugin = await loadPlugin(req.body.plugin as string);
```

Create a typed map of plugin loaders and validate the name before
invoking the loader.

## Safe Express routing with typed handlers

### Vulnerable

```typescript
interface Route {
    [action: string]: (req: Request, res: Response) => void;
}

const routes: Route = {
    create: handleCreate,
    delete: handleDelete,
};

app.get('/:action', (req, res) => {
    const handler = routes[req.params.action];
    if (handler) handler(req, res);
});
```

### Safe

```typescript
type ActionName = 'create' | 'delete' | 'update';

const routes: Record<ActionName, Handler> = {
    create: handleCreate,
    delete: handleDelete,
    update: handleUpdate,
};

app.get('/create', (req, res) => handleCreate(req, res));
app.get('/delete', (req, res) => handleDelete(req, res));
app.get('/update', (req, res) => handleUpdate(req, res));
```

Define explicit routes for each action. Avoid parameterizing the
handler name from the URL.

## Safe property access with type guards

### Vulnerable

```typescript
interface Config {
    [key: string]: string;
}

const key = req.body.key as string;
const value = (config as any)[key];
```

### Safe

```typescript
type ConfigKey = 'host' | 'port' | 'timeout';

const config: Record<ConfigKey, string> = {
    host: 'localhost',
    port: '3000',
    timeout: '5000',
};

function isConfigKey(key: unknown): key is ConfigKey {
    return key === 'host' || key === 'port' || key === 'timeout';
}

const key = req.body.key;
if (!isConfigKey(key)) {
    throw new Error('Invalid config key');
}
const value = config[key];
```

Use a type guard to validate property names before access. This
combines type safety with runtime validation.

## Safe switch pattern with exhaustiveness checking

### Vulnerable

```typescript
type Operation = string;

async function calculate(op: Operation, a: number, b: number) {
    const handlers: Record<string, () => number> = {
        add: () => a + b,
        subtract: () => a - b,
    };
    return handlers[op]();
}
```

### Safe

```typescript
type Operation = 'add' | 'subtract' | 'multiply' | 'divide';

function calculate(op: Operation, a: number, b: number): number {
    switch (op) {
        case 'add':
            return a + b;
        case 'subtract':
            return a - b;
        case 'multiply':
            return a * b;
        case 'divide':
            if (b === 0) throw new Error('Division by zero');
            return a / b;
    }
}

const op = req.query.op as Operation;
const result = calculate(op, 10, 5);
```

Use a discriminated union and switch statement. TypeScript enforces
exhaustiveness; every case is handled.
