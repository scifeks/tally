# PHP open redirect patterns

Vulnerable-vs-safe snippets for the PHP web frameworks the
`access_control.open_redirect` scanner recognizes.

## Raw PHP with header()

### Vulnerable

```php
$redirect_to = $_GET['url'];
header('Location: ' . $redirect_to);
exit;
```

### Safe

```php
$redirect_to = $_GET['url'];
$allowed = ['https://example.com', 'https://app.example.com'];

if (in_array($redirect_to, $allowed, true)) {
    header('Location: ' . $redirect_to);
} else {
    header('Location: /dashboard');
}
exit;
```

Always validate the redirect destination before passing it to
`header('Location: ...')`. For relative paths, verify the path
starts with `/` and does not contain a domain.

## Laravel

### Vulnerable

```php
public function login(Request $request)
{
    $url = $request->input('redirect');
    return redirect()->to($url);
}

public function go(Request $request)
{
    return redirect($request->input('next'));
}
```

### Safe

```php
public function login(Request $request)
{
    $url = $request->input('redirect', '/dashboard');
    $allowed = ['https://example.com', 'https://app.example.com'];

    if (in_array($url, $allowed, true)) {
        return redirect($url);
    }

    return redirect('/dashboard');
}

public function go(Request $request)
{
    $next = $request->input('next', 'dashboard');
    if (str_starts_with($next, '/')) {
        return redirect($next);
    }
    return redirect(route('dashboard'));
}
```

Laravel's `redirect()` and `redirect()->to()` do not validate the
destination. Check the URL against an allowlist before redirecting,
or use `route()` to generate safe internal redirects.

## WordPress

### Vulnerable

```php
$redirect_to = $_REQUEST['redirect_to'];
wp_redirect($redirect_to);
exit;
```

### Safe

```php
$redirect_to = $_REQUEST['redirect_to'];
$redirect_to = wp_validate_redirect($redirect_to, admin_url());

wp_redirect($redirect_to);
exit;
```

WordPress's `wp_validate_redirect()` checks the URL and returns the
safe destination or a fallback. Always use its return value. The
second argument is the fallback if validation fails.

## Symfony

### Vulnerable

```php
namespace App\Controller;

use Symfony\Component\HttpFoundation\RedirectResponse;

class AuthController
{
    public function login(Request $request)
    {
        $url = $request->query->get('return_to');
        return new RedirectResponse($url);
    }
}
```

### Safe

```php
namespace App\Controller;

use Symfony\Component\HttpFoundation\RedirectResponse;

class AuthController
{
    private array $allowedHosts = ['example.com', 'app.example.com'];

    public function login(Request $request)
    {
        $url = $request->query->get('return_to', '/');
        $parsed = parse_url($url);

        if (isset($parsed['host']) &&
            !in_array($parsed['host'], $this->allowedHosts,
            true)) {
            $url = '/';
        }

        if (!isset($parsed['host']) && str_starts_with($url, '/')) {
            return new RedirectResponse($url);
        }

        if (!isset($parsed['host'])) {
            $url = '/';
        }

        return new RedirectResponse($url);
    }
}
```

Parse the URL with `parse_url()` and check the host against an
allowlist. Relative paths (no host) can be allowed if they start
with `/`.

## Relative-path-only redirect (safe)

```php
$page = $_GET['page'] ?? 'home';
$allowed_pages = ['home', 'about', 'contact'];

if (!in_array($page, $allowed_pages, true)) {
    $page = 'home';
}

header('Location: /' . $page);
exit;
```

Redirects to relative paths that do not include a host are
inherently same-origin and safe.

## Anti-pattern: missing return value check

```php
$redirect_to = $_REQUEST['redirect_to'];
wp_validate_redirect($redirect_to);
wp_redirect($redirect_to);
exit;
```

The `wp_validate_redirect()` return value is ignored. The original,
unvalidated `$redirect_to` is passed to `wp_redirect()`. Always
assign the return value to a variable and use that for the redirect.
