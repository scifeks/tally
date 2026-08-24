# PHP CSP misconfiguration patterns

Vulnerable-vs-safe snippets for PHP web frameworks the `misconfig.csp`
scanner recognizes. When multiple safe forms exist, the canonical one is
shown first.

## Laravel middleware

### Vulnerable

```php
// app/Http/Middleware/SetSecurityHeaders.php

public function handle($request, Closure $next)
{
    $response = $next($request);
    // No Content-Security-Policy header is set
    return $response;
}
```

### Safe

```php
// app/Http/Middleware/SetSecurityHeaders.php

public function handle($request, Closure $next)
{
    $response = $next($request);
    $csp = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' https://fonts.googleapis.com"
    );
    $response->headers->set('Content-Security-Policy', $csp);
    return $response;
}
```

Set a restrictive CSP header in a middleware that all routes pass through.
Register the middleware in `app/Http/Kernel.php` within the `$middleware`
array.

## Laravel header permissive

### Vulnerable

```php
// app/Http/Middleware/SetSecurityHeaders.php

public function handle($request, Closure $next)
{
    $response = $next($request);
    $response->headers->set(
        'Content-Security-Policy',
        "default-src *; script-src * 'unsafe-inline'"
    );
    return $response;
}
```

### Safe

```php
// app/Http/Middleware/SetSecurityHeaders.php

public function handle($request, Closure $next)
{
    $response = $next($request);
    $csp = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' https://fonts.googleapis.com"
    );
    $response->headers->set('Content-Security-Policy', $csp);
    return $response;
}
```

Replace wildcard sources with `'self'`. Remove `'unsafe-inline'` and
`'unsafe-eval'` unless the application requires them, and consider using a
nonce-based policy instead.

## Symfony NelmioSecurityBundle

### Vulnerable

```yaml
# config/packages/nelmio_security.yaml

nelmio_security:
  csp:
    default_src: ['*']
    script_src: ['*', "'unsafe-inline'"]
    style_src: ['*', "'unsafe-eval'"]
```

### Safe

```yaml
# config/packages/nelmio_security.yaml

nelmio_security:
  csp:
    default_src: ["'self'"]
    script_src: ["'self'"]
    style_src: ["'self'", "https://fonts.googleapis.com"]
    report_uri: "/csp-report"
```

Configure CSP directives to restrict sources to `'self'` and add specific
trusted origins only as needed. Set `report_uri` to capture CSP violations
for monitoring.

## Manual header() permissive

### Vulnerable

```php
// config/security.php or any controller

header('Content-Security-Policy: default-src * ; script-src * "unsafe-inline"');
```

### Safe

```php
// config/security.php or a security middleware

header(
    'Content-Security-Policy: '
    . "default-src 'self'; "
    . "script-src 'self'; "
    . "style-src 'self' https://fonts.googleapis.com"
);
```

Use a restrictive CSP header with `default-src 'self'` and specific directives
for scripts and styles. Move the header call into early-execution middleware
or a bootstrap script to ensure it applies to all responses.
