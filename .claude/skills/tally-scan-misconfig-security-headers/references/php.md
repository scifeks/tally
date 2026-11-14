# PHP missing security headers patterns

Vulnerable-vs-safe snippets for PHP web frameworks the
`misconfig.security_headers` scanner recognizes. When multiple safe forms
exist, the canonical one is shown first.

## Laravel middleware

### Vulnerable

```php
// routes/web.php or app/Http/Controllers/ApiController.php
Route::get('/api/user', function (Request $request) {
    return response()->json(['id' => 1, 'name' => 'Alice']);
});

// No middleware applies security headers by default
```

### Safe

```php
// app/Http/Middleware/SecurityHeadersMiddleware.php
namespace App\Http\Middleware;

use Closure;

class SecurityHeadersMiddleware
{
    public function handle($request, Closure $next)
    {
        $response = $next($request);
        $response->header('X-Content-Type-Options', 'nosniff');
        $response->header('X-Frame-Options', 'DENY');
        $response->header(
            'Strict-Transport-Security',
            'max-age=31536000; includeSubDomains'
        );
        $response->header(
            'Referrer-Policy',
            'strict-origin-when-cross-origin'
        );
        return $response;
    }
}

// app/Http/Kernel.php
protected $middleware = [
    \App\Http\Middleware\SecurityHeadersMiddleware::class,
];

// routes/web.php
Route::get('/api/user', function (Request $request) {
    return response()->json(['id' => 1, 'name' => 'Alice']);
});
```

Create a middleware that adds X-Content-Type-Options, X-Frame-Options,
Strict-Transport-Security, and Referrer-Policy headers to every response.
Register it in app/Http/Kernel.php in the $middleware array to apply it
globally.

## Symfony NelmioSecurityBundle

### Vulnerable

```yaml
# config/packages/security.yaml (no nelmio config)
security:
    password_hashers:
        Symfony\Component\Security\Core\User\PasswordAuthenticatedUserInterface: 'auto'
```

### Safe

```yaml
# config/packages/nelmio_security.yaml
nelmio_security:
    forced_https: true
    referrer_policy:
        policies:
            - strict-origin-when-cross-origin
    response:
        x_content_type_options: nosniff
        x_frame_options: DENY
    hsts:
        max_age: 31536000
        include_subdomains: true
    content_type:
        charset: UTF-8
```

Install and configure NelmioSecurityBundle. Set x_content_type_options,
x_frame_options, forced_https, and hsts in
config/packages/nelmio_security.yaml. The bundle automatically injects
these headers on all responses.

## Manual header() calls

### Vulnerable

```php
// app/Http/Controllers/UserController.php
class UserController
{
    public function show($id)
    {
        header('Content-Type: application/json');
        echo json_encode(['id' => $id, 'name' => 'Alice']);
    }
}
```

### Safe

```php
// app/Http/Middleware/SecurityHeadersMiddleware.php
namespace App\Http\Middleware;

class SecurityHeadersMiddleware
{
    public function setHeaders()
    {
        header('X-Content-Type-Options: nosniff');
        header('X-Frame-Options: DENY');
        header(
            'Strict-Transport-Security: max-age=31536000; ' .
            'includeSubDomains'
        );
        header(
            'Referrer-Policy: strict-origin-when-cross-origin'
        );
    }
}

// app/Http/Controllers/UserController.php
class UserController
{
    public function show($id)
    {
        $middleware = new \App\Http\Middleware\SecurityHeadersMiddleware();
        $middleware->setHeaders();
        header('Content-Type: application/json');
        echo json_encode(['id' => $id, 'name' => 'Alice']);
    }
}
```

Create a helper function or middleware method that calls header() to set
X-Content-Type-Options, X-Frame-Options, Strict-Transport-Security, and
Referrer-Policy. Call this function at the start of every response,
before sending output.

## Slim Framework

### Vulnerable

```php
// index.php
use Psr\Http\Message\ResponseInterface as Response;
use Psr\Http\Message\ServerRequestInterface as Request;
use Slim\Factory\AppFactory;

$app = AppFactory::create();

$app->get('/', function (Request $request, Response $response) {
    $response->getBody()->write('Hello');
    return $response;
});

$app->run();
```

### Safe

```php
// Middleware/SecurityHeadersMiddleware.php
namespace Middleware;

use Psr\Http\Message\ResponseInterface;
use Psr\Http\Message\ServerRequestInterface;
use Psr\Http\Server\MiddlewareInterface;
use Psr\Http\Server\RequestHandlerInterface;

class SecurityHeadersMiddleware implements MiddlewareInterface
{
    public function process(
        ServerRequestInterface $request,
        RequestHandlerInterface $handler
    ): ResponseInterface {
        $response = $handler->handle($request);
        return $response
            ->withHeader('X-Content-Type-Options', 'nosniff')
            ->withHeader('X-Frame-Options', 'DENY')
            ->withHeader(
                'Strict-Transport-Security',
                'max-age=31536000; includeSubDomains'
            )
            ->withHeader(
                'Referrer-Policy',
                'strict-origin-when-cross-origin'
            );
    }
}

// index.php
use Psr\Http\Message\ResponseInterface as Response;
use Psr\Http\Message\ServerRequestInterface as Request;
use Slim\Factory\AppFactory;
use Middleware\SecurityHeadersMiddleware;

$app = AppFactory::create();
$app->add(new SecurityHeadersMiddleware());

$app->get('/', function (Request $request, Response $response) {
    $response->getBody()->write('Hello');
    return $response;
});

$app->run();
```

Implement MiddlewareInterface and use the withHeader() method to add
security headers to the response. Register the middleware with the app
using $app->add().
