# PHP unsafe reflection patterns

Vulnerable-vs-safe snippets for the PHP reflection and dynamic
invocation mechanisms the `injection.reflection` scanner recognizes.
When multiple safe forms exist, the canonical one is shown first.

## Variable class instantiation

### Vulnerable

```php
$class = $_GET['class'];
$obj = new $class();

$controllerName = request()->query->get('controller');
$controller = new $controllerName();
```

### Safe

```php
$allowedClasses = ['UserHandler', 'AdminHandler', 'GuestHandler'];
$class = $_GET['class'] ?? null;
if (!in_array($class, $allowedClasses, true)) {
    throw new InvalidArgumentException("Class not allowed");
}
$obj = new $class();
```

Maintain an allowlist of permitted classes. Check the input against
the list before instantiation. For better type safety, use a factory
pattern.

## Safe factory pattern

### Vulnerable

```php
$handler = new $_GET['handler']();
$handler->process();
```

### Safe

```php
class HandlerFactory {
    private const HANDLERS = [
        'create' => CreateHandler::class,
        'delete' => DeleteHandler::class,
        'update' => UpdateHandler::class,
    ];

    public static function create(string $name): HandlerInterface {
        $class = self::HANDLERS[$name] ?? null;
        if ($class === null) {
            throw new InvalidArgumentException("Unknown handler");
        }
        return new $class();
    }
}

$handler = HandlerFactory::create($_GET['handler']);
```

Use a factory that maps safe identifiers to actual class names.
The mapping is explicit and cannot be bypassed.

## Variable function call

### Vulnerable

```php
$func = $_GET['function'];
$result = $func();

$action = request()->input('action');
echo $action();
```

### Safe

```php
$allowedFunctions = [
    'getUser' => fn($id) => User::find($id),
    'listUsers' => fn() => User::all(),
    'deleteUser' => fn($id) => User::destroy($id),
];

$action = $_GET['action'] ?? null;
if (!isset($allowedFunctions[$action])) {
    throw new InvalidArgumentException("Action not allowed");
}
$result = $allowedFunctions[$action]();
```

Build a dispatch array mapping safe action names to closures. Check
the user input against the array before invocation.

## call_user_func with user input

### Vulnerable

```php
$callback = $_GET['method'];
$result = call_user_func($callback, $arg1, $arg2);

$handler = $_POST['handler'];
call_user_func([$obj, $handler], $data);
```

### Safe

```php
$handlers = [
    'process_order' => fn($order) => OrderProcessor::process($order),
    'send_email' => fn($email, $data) => Mailer::send($email, $data),
];

$method = $_GET['method'] ?? null;
if (!isset($handlers[$method])) {
    throw new InvalidArgumentException("Handler not found");
}
$result = $handlers[$method](...);
```

Never pass untrusted user input directly to `call_user_func()`.
Use a dispatch map of allowed callbacks.

## ReflectionClass from user input

### Vulnerable

```php
$className = $_GET['class'];
$reflect = new ReflectionClass($className);
$obj = $reflect->newInstance();

$method = request()->input('method');
$reflectionMethod = new ReflectionMethod($class, $method);
```

### Safe

```php
$allowedClasses = ['Service1', 'Service2', 'Service3'];
$className = $_GET['class'] ?? null;
if (!in_array($className, $allowedClasses, true)) {
    throw new InvalidArgumentException("Class not allowed");
}
$reflect = new ReflectionClass($className);
$obj = $reflect->newInstance();
```

Before constructing a ReflectionClass or ReflectionMethod from user
input, validate the class or method name against an allowlist.

## Safe Laravel route-model binding

### Vulnerable

```php
Route::get('/resource/{action}', function($action) {
    $method = 'handle' . ucfirst($action);
    return (new ResourceHandler)->$method();
});
```

### Safe

```php
Route::get('/resource/create', function() {
    return (new ResourceHandler)->handleCreate();
});

Route::get('/resource/delete', function() {
    return (new ResourceHandler)->handleDelete();
});
```

Use explicit, separate routes for each action. Avoid parameterizing
the method name from the URL.

## Safe PSR container pattern

### Vulnerable

```php
$serviceName = $_GET['service'];
$service = $container->get($serviceName);
```

### Safe

```php
$allowedServices = ['mailer', 'logger', 'cache'];
$serviceName = $_GET['service'] ?? null;
if (!in_array($serviceName, $allowedServices, true)) {
    throw new InvalidArgumentException("Service not available");
}
$service = $container->get($serviceName);
```

Even when using a DI container, validate service names against an
allowlist before retrieval.
