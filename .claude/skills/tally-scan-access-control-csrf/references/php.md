# PHP CSRF patterns

Vulnerable-vs-safe snippets for the PHP frameworks the
`access_control.csrf` scanner recognizes. When multiple safe forms exist,
the canonical one is shown first.

## Laravel

### Vulnerable

```php
// app/Http/Middleware/VerifyCsrfToken.php
protected $except = [
    'api/user/update',
];
```

```php
// In a route file
Route::post('/user/update', 'UserController@update');
// Route group without 'web' middleware
Route::group(['prefix' => 'api'], function () {
    Route::post('/user/update', 'UserController@update');
});
```

### Safe

```php
// app/Http/Middleware/VerifyCsrfToken.php
protected $except = [
    'webhook/*',  // Only for routes with external verification
];
```

```php
// In a route file
Route::post('/user/update', 'UserController@update');
// Routes in the 'web' middleware group include CSRF verification
Route::group(['middleware' => 'web'], function () {
    Route::post('/user/update', 'UserController@update');
});
```

In the Blade template:

```blade
<form method="post" action="{{ route('user.update') }}">
    @csrf
    <input type="text" name="name">
    <input type="submit">
</form>
```

Laravel's `VerifyCsrfToken` middleware is included in the `web` middleware
group by default. Do not add routes to the `$except` array unless they
have alternative authentication (e.g. webhook signatures). Always include
the `@csrf` Blade directive in forms or the `X-CSRF-TOKEN` header in
AJAX requests.

## Symfony

### Vulnerable

```php
use Symfony\Component\Form\Extension\Core\Type\SubmitType;

$form = $this->createForm(UserType::class, $user, [
    'csrf_protection' => false,
]);
```

### Safe

```php
use Symfony\Component\Form\Extension\Core\Type\SubmitType;

$form = $this->createForm(UserType::class, $user);
// CSRF protection is enabled by default
```

In the Twig template:

```twig
{{ form_start(form) }}
    {{ form_widget(form) }}
    <button type="submit">Update</button>
{{ form_end(form) }}
```

Symfony enables CSRF protection by default for all forms. Do not set
`csrf_protection` to false. The `form_end` Twig function automatically
includes the CSRF token field.

## Raw PHP

### Vulnerable

```php
session_start();
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $name = $_POST['name'];
    // No token validation
    $user->name = $name;
    $user->save();
    echo "Updated";
}
```

### Safe

```php
session_start();

if ($_SERVER['REQUEST_METHOD'] === 'GET') {
    if (empty($_SESSION['csrf_token'])) {
        $_SESSION['csrf_token'] = bin2hex(random_bytes(32));
    }
    $token = $_SESSION['csrf_token'];
    echo "<form method='post'>
            <input type='hidden' name='csrf_token' value='$token'>
            <input type='text' name='name'>
            <input type='submit'>
          </form>";
}

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $token = $_POST['csrf_token'] ?? '';
    if (empty($_SESSION['csrf_token']) ||
        !hash_equals($_SESSION['csrf_token'], $token)) {
        http_response_code(403);
        echo "CSRF token invalid";
        exit;
    }
    $name = $_POST['name'];
    $user->name = $name;
    $user->save();
    echo "Updated";
}
```

Generate a unique token per session on GET requests and store it in the
session. Validate the token on POST using `hash_equals` for
constant-time comparison. Regenerate the token after each successful
submission.

## WordPress

### Vulnerable

```php
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    global $wpdb;
    $name = $_POST['name'];
    // No nonce verification
    $wpdb->update('wp_users', ['user_nicename' => $name],
        ['ID' => get_current_user_id()]);
    echo "Updated";
}
```

### Safe

```php
if ($_SERVER['REQUEST_METHOD'] === 'GET') {
    $nonce = wp_create_nonce('update_user');
    echo "<form method='post'>
            <input type='hidden' name='user_nonce' value='$nonce'>
            <input type='text' name='name'>
            <input type='submit'>
          </form>";
}

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    if (!isset($_POST['user_nonce']) ||
        !wp_verify_nonce($_POST['user_nonce'], 'update_user')) {
        wp_die('Security check failed');
    }
    $name = sanitize_text_field($_POST['name']);
    global $wpdb;
    $wpdb->update('wp_users', ['user_nicename' => $name],
        ['ID' => get_current_user_id()]);
    echo "Updated";
}
```

WordPress provides the `wp_create_nonce` and `wp_verify_nonce` functions
for CSRF protection. Generate a nonce on GET, verify it on POST. Always
sanitize user input with `sanitize_*` functions.
