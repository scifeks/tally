# PHP error message exposure patterns

Vulnerable-vs-safe snippets for PHP error handling the
`misconfig.error_message_exposure` scanner recognizes. When multiple safe
forms exist, the canonical one is shown first.

## PHP display_errors setting

### Vulnerable

```php
<?php
ini_set('display_errors', '1');
ini_set('display_startup_errors', '1');

try {
    $data = fetch_data();
} catch (Exception $e) {
    // Errors display directly to the browser
}
```

### Safe

```php
<?php
ini_set('display_errors', '0');
ini_set('log_errors', '1');
ini_set('error_log', '/var/log/php-errors.log');

try {
    $data = fetch_data();
} catch (Exception $e) {
    error_log("Error: " . $e->getMessage());
    http_response_code(500);
    echo json_encode(["error" => "Internal server error"]);
}
```

Set `display_errors = Off` in php.ini for production. Log errors to a file
instead. Return generic error messages in the HTTP response.

## Custom exception handlers

### Vulnerable

```php
<?php
set_exception_handler(function (Throwable $e) {
    header('Content-Type: application/json');
    http_response_code(500);
    echo json_encode([
        "error" => $e->getMessage(),
        "trace" => $e->getTraceAsString()
    ]);
});

throw new Exception("Database connection failed");
```

### Safe

```php
<?php
set_exception_handler(function (Throwable $e) {
    error_log("Exception: " . $e->getMessage());
    header('Content-Type: application/json');
    http_response_code(500);
    echo json_encode([
        "error" => "Internal server error"
    ]);
});

throw new Exception("Database connection failed");
```

In custom exception handlers, log the full exception server-side. Return a
generic error message in the HTTP response without exposing exception
details or stack traces.

## Laravel exception rendering

### Vulnerable

```php
<?php
namespace App\Exceptions;

class Handler extends ExceptionHandler
{
    public function render($request, Throwable $e)
    {
        if ($request->expectsJson()) {
            return response()->json([
                'error' => $e->getMessage(),
                'trace' => $e->getTraceAsString()
            ], 500);
        }
    }
}
```

### Safe

```php
<?php
namespace App\Exceptions;

class Handler extends ExceptionHandler
{
    public function render($request, Throwable $e)
    {
        if ($request->expectsJson()) {
            \Log::error("Exception: " . $e->getMessage());
            return response()->json([
                'error' => 'Internal server error'
            ], 500);
        }
    }
}
```

In the exception handler's render method, log the full exception using
`\Log::error()` or similar. Return a generic error message without exposing
exception details.

## WordPress error handling

### Vulnerable

```php
<?php
if (!isset($_GET['id'])) {
    $db_result = $wpdb->get_results("SELECT * FROM users WHERE id = ...");
    if (!$db_result) {
        wp_die($wpdb->last_error);
    }
}
```

### Safe

```php
<?php
if (!isset($_GET['id'])) {
    $db_result = $wpdb->get_results("SELECT * FROM users WHERE id = ...");
    if (!$db_result) {
        error_log("Database error: " . $wpdb->last_error);
        wp_die("An error occurred. Please try again later.", 500);
    }
}
```

Log database errors using `error_log()`. Return a generic error message to
the user with `wp_die()` or a custom error page without exposing database
details.

## Bare exception handlers

### Vulnerable

```php
<?php
try {
    $data = json_decode($json, true);
} catch (JsonException $e) {
    http_response_code(400);
    echo json_encode(["error" => $e->getMessage()]);
}
```

### Safe

```php
<?php
try {
    $data = json_decode($json, true);
} catch (JsonException $e) {
    error_log("JSON decode error: " . $e->getMessage());
    http_response_code(400);
    echo json_encode(["error" => "Invalid JSON"]);
}
```

Catch specific exception types. Log the exception server-side. Return a
generic error message that describes the error class (e.g., "Invalid JSON")
without exposing the exception message.
