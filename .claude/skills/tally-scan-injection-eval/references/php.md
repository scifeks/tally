# PHP code injection patterns

Vulnerable-vs-safe snippets for the PHP eval, assert, create_function,
and preg_replace functions the `injection.eval` scanner recognizes.

## eval() function

### Vulnerable

```php
$code = $_GET["php"];
eval($code);

$template = "echo '$user_input';";
eval($template);
```

### Safe

```php
$data = $_GET["json"];
$obj = json_decode($data, true);

switch ($_GET["action"]) {
    case "search":
        searchUsers($query);
        break;
    case "delete":
        deleteUser($id);
        break;
    default:
        throw new Exception("Invalid action");
}
```

`eval()` parses and executes a string as PHP code. Never pass user
input to it. Instead, use a switch statement or associative array to
dispatch to allowed functions.

## assert() function

### Vulnerable (PHP < 8.0)

```php
$assertion = $_POST["check"];
assert($assertion);
```

### Safe

```php
if (!$user_valid) {
    throw new Exception("Assertion failed");
}
```

In PHP < 8.0 with `assert.active=1` (non-default but legacy configs),
`assert()` treats its argument as PHP code. In PHP 8.0+, `assert()` is
a language construct and is safe. Audit legacy codebases for
`assert.active` settings in `php.ini` or `.htaccess`.

## create_function()

### Vulnerable

```php
$body = $_POST["body"];
$func = create_function('$x', $body);
$func(10);
```

### Safe

```php
$func = function ($x) use ($default_value) {
    return $x + $default_value;
};
$func(10);

$callbacks = [
    "add" => function ($a, $b) { return $a + $b; },
    "multiply" => function ($a, $b) { return $a * $b; },
];
```

`create_function()` is deprecated and creates a function from a string.
The second argument is evaluated as PHP code. The function was removed
in PHP 8.0. Use anonymous functions or a callback array instead.

## preg_replace() with /e flag

### Vulnerable (PHP < 7.0)

```php
$pattern = '/.*/';
$replacement = $_POST["expr"];
preg_replace($pattern, $replacement, $subject, -1, 1, PREG_REPLACE_EVAL);

preg_replace('/(.*)/, $1 + $expr', $text);
```

### Safe

```php
$pattern = '/.*/';
$replacement = htmlspecialchars($_POST["expr"]);
$result = preg_replace($pattern, $replacement, $subject);

$pattern = '/.*/';
$callback = function ($matches) use ($expr) {
    return $matches[1] . " + " . $expr;
};
$result = preg_replace_callback($pattern, $callback, $text);
```

The `/e` flag (removed in PHP 7.0) and the `PREG_REPLACE_EVAL` option
cause the replacement string to be evaluated as PHP code. Use
`preg_replace_callback()` instead, passing a closure that constructs
the replacement string safely.

## Dynamic function dispatch (safe pattern)

If you need to call a method dynamically based on user input, build
a whitelist of allowed class and method names:

```php
$ALLOWED_METHODS = [
    "UserController" => ["list", "create", "delete"],
    "AdminController" => ["dashboard", "audit"],
];

$controller = $_GET["controller"];
$method = $_GET["method"];

if (!isset($ALLOWED_METHODS[$controller]) ||
    !in_array($method, $ALLOWED_METHODS[$controller])) {
    throw new Exception("Access denied");
}

$obj = new $controller();
$obj->$method();
```

The nested array acts as an allowlist. Only predefined methods can be
invoked, regardless of user input.
