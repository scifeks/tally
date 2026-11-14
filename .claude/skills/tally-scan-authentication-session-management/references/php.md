# PHP session management patterns

Vulnerable-vs-safe snippets for PHP native sessions and Laravel
that the `authentication.session_management` scanner recognizes.

## PHP native: session fixation

### Vulnerable

```php
session_start();
if (authenticate($username, $password)) {
    $_SESSION['user_id'] = $user->id;
    header('Location: /dashboard');
}
```

### Safe

```php
session_start();
if (authenticate($username, $password)) {
    session_regenerate_id(true);
    $_SESSION['user_id'] = $user->id;
    header('Location: /dashboard');
}
```

The `true` argument to `session_regenerate_id()` deletes the old
session file. Without it, the old session ID remains valid.

## PHP native: insecure cookie flags

### Vulnerable

```php
session_start();
```

### Safe

```php
session_set_cookie_params([
    'lifetime' => 3600,
    'path' => '/',
    'secure' => true,
    'httponly' => true,
    'samesite' => 'Lax',
]);
session_start();
```

Call `session_set_cookie_params()` before `session_start()`. The
array form (PHP 7.3+) is clearer than the positional-argument
form.

## PHP native: session ID in URL

### Vulnerable

```ini
; php.ini
session.use_trans_sid = 1
session.use_only_cookies = 0
```

### Safe

```ini
; php.ini
session.use_trans_sid = 0
session.use_only_cookies = 1
session.use_strict_mode = 1
```

`use_trans_sid` appends the session ID to every URL as a query
parameter. `use_strict_mode` rejects uninitialized session IDs,
which blocks fixation via cookie injection.

## Laravel: session fixation

### Vulnerable

```php
public function login(Request $request)
{
    $credentials = $request->only('email', 'password');
    $user = User::where('email', $credentials['email'])
        ->first();
    if ($user && Hash::check($credentials['password'], $user->password)) {
        $request->session()->put('user_id', $user->id);
        return redirect('/dashboard');
    }
}
```

### Safe

```php
public function login(Request $request)
{
    $credentials = $request->only('email', 'password');
    if (Auth::attempt($credentials)) {
        $request->session()->regenerate();
        return redirect('/dashboard');
    }
}
```

`Auth::attempt()` handles credential verification and session
management. If you bypass `Auth::attempt()`, call
`$request->session()->regenerate()` after authentication.

## Laravel: session cookie configuration

### Vulnerable

```php
// config/session.php
'secure' => false,
'http_only' => false,
'same_site' => null,
```

### Safe

```php
// config/session.php
'secure' => env('SESSION_SECURE_COOKIE', true),
'http_only' => true,
'same_site' => 'lax',
'lifetime' => 120,
```

Laravel's default `lifetime` is 120 minutes. Shorten it for
sensitive applications.
