# PHP order-of-operations patterns

Vulnerable-vs-safe snippets for PHP frameworks that the
`design_logic.order_of_operations` scanner recognizes.

## Laravel middleware registration order

### Vulnerable

```php
Route::middleware(['authorize', 'authenticate'])->group(function () {
    Route::get('/admin', [AdminController::class, 'dashboard']);
});
```

Middleware executes in registration order. `authorize` runs first,
then `authenticate`. An unauthenticated user reaches the authorization
check before being authenticated.

### Safe

```php
Route::middleware(['authenticate', 'authorize'])->group(function () {
    Route::get('/admin', [AdminController::class, 'dashboard']);
});
```

Middleware executes in registration order: `authenticate` first, then
`authorize`. The user is authenticated before permission is checked.

Alternatively, use a combined middleware:

```php
Route::middleware(['auth'])->group(function () {
    Route::middleware(['role:admin'])->group(function () {
        Route::get('/admin', [AdminController::class, 'dashboard']);
    });
});
```

## Eloquent save before validation

### Vulnerable

```php
public function store(Request $request)
{
    $user = new User();
    $user->email = $request->email;
    $user->name = $request->name;
    $user->save();
    
    $validator = Validator::make($request->all(), [
        'email' => 'email',
        'name' => 'required',
    ]);
    
    if ($validator->fails()) {
        throw new ValidationException($validator);
    }
}
```

The user is saved to the database before validation. Invalid data is
persisted.

### Safe

```php
public function store(Request $request)
{
    $validator = Validator::make($request->all(), [
        'email' => 'email',
        'name' => 'required',
    ]);
    
    if ($validator->fails()) {
        throw new ValidationException($validator);
    }
    
    $user = new User();
    $user->email = $request->email;
    $user->name = $request->name;
    $user->save();
}
```

Validation runs before persistence. Only valid data reaches the
database.

Alternatively, use Laravel's automatic validation:

```php
public function store(Request $request)
{
    $validated = $request->validate([
        'email' => 'email',
        'name' => 'required',
    ]);
    
    User::create($validated);
}
```

## Output before HTML encoding

### Vulnerable

```php
function display_comment($comment_text) {
    echo "<p>" . $comment_text . "</p>";
    $safe_text = htmlspecialchars($comment_text);
}
```

The raw comment is output before HTML encoding. XSS is possible.

### Safe

```php
function display_comment($comment_text) {
    $safe_text = htmlspecialchars($comment_text, ENT_QUOTES, 'UTF-8');
    echo "<p>" . $safe_text . "</p>";
}
```

HTML encoding runs before output. Only safe text reaches the browser.

## File operation before path validation

### Vulnerable

```php
function save_user_file($filename, $content) {
    file_put_contents("/uploads/" . $filename, $content);
    
    if (strpos($filename, "..") !== false) {
        throw new Exception("Invalid filename");
    }
}
```

The file is written before path validation. A path traversal payload
(e.g., `../../etc/passwd`) reaches the filesystem before validation.

### Safe

```php
function save_user_file($filename, $content) {
    if (strpos($filename, "..") !== false) {
        throw new Exception("Invalid filename");
    }
    
    file_put_contents("/uploads/" . $filename, $content);
}
```

Path validation runs before the write. Only safe paths reach the
filesystem.

Alternatively, use basename to strip directory components:

```php
function save_user_file($filename, $content) {
    $safe_filename = basename($filename);
    file_put_contents("/uploads/" . $safe_filename, $content);
}
```

## Symfony voter / firewall ordering

### Vulnerable

```php
// In security.yaml
security:
    firewalls:
        api:
            pattern: ^/api
            stateless: true
            anonymous: ~
            access_control:
                - { path: ^/api/admin, roles: ROLE_ADMIN }
                - { path: ^/api/admin, roles: IS_AUTHENTICATED }
```

The `access_control` list is evaluated in order. If the admin route
check runs before the authentication check, an unauthenticated request
reaches the role check.

### Safe

```php
security:
    firewalls:
        api:
            pattern: ^/api
            stateless: true
            access_control:
                - { path: ^/api/admin, roles: IS_AUTHENTICATED }
                - { path: ^/api/admin, roles: ROLE_ADMIN }
```

Authentication is checked before role-based access. Or, combine the
checks:

```php
access_control:
    - { path: ^/api/admin, roles: 'ROLE_ADMIN' }
```

Symfony resolves `ROLE_ADMIN` only if the user is authenticated.

## Generic PSR middleware stack

### Vulnerable

```php
$app->pipe(AuthorizeMiddleware::class);
$app->pipe(AuthenticateMiddleware::class);
$app->pipe(RequestHandler::class);
```

Middleware executes in registration order. `AuthorizeMiddleware` runs
before `AuthenticateMiddleware`. An unauthenticated request reaches
the authorization check.

### Safe

```php
$app->pipe(AuthenticateMiddleware::class);
$app->pipe(AuthorizeMiddleware::class);
$app->pipe(RequestHandler::class);
```

Middleware executes in order: `AuthenticateMiddleware` first, then
`AuthorizeMiddleware`. The user is authenticated before permission is
checked.

## WordPress permission before authentication

### Vulnerable

```php
function get_admin_page() {
    if (!current_user_can('manage_options')) {
        wp_die('Unauthorized');
    }
    
    if (!is_user_logged_in()) {
        wp_redirect(wp_login_url());
        exit;
    }
    
    return render_admin_page();
}
```

Permission is checked before login status. An unauthenticated user
might bypass the permission check depending on the state of
`current_user_can()`.

### Safe

```php
function get_admin_page() {
    if (!is_user_logged_in()) {
        wp_redirect(wp_login_url());
        exit;
    }
    
    if (!current_user_can('manage_options')) {
        wp_die('Unauthorized');
    }
    
    return render_admin_page();
}
```

Authentication is checked before permission. Only logged-in users
reach the permission check.

Alternatively, use WordPress hooks:

```php
add_action('admin_init', function() {
    if (!current_user_can('manage_options')) {
        wp_die('Unauthorized');
    }
});
```

The `admin_init` hook already enforces `is_user_logged_in()`.
