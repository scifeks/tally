# PHP authentication patterns

Vulnerable-vs-safe snippets for Laravel and Symfony that the
`authentication.weak_or_missing_authn` scanner recognizes.

## Laravel: missing route middleware

### Vulnerable

```php
// routes/web.php
Route::get('/admin/users', [AdminController::class, 'index']);
```

### Safe

```php
// routes/web.php
Route::middleware('auth')->group(function () {
    Route::get('/admin/users', [AdminController::class, 'index']);
});
```

Apply `auth` middleware to the route or its enclosing group.
For API routes, use `auth:sanctum` or `auth:api`.

## Laravel: missing controller middleware

### Vulnerable

```php
class AdminController extends Controller
{
    public function index()
    {
        return User::all();
    }
}
```

### Safe

```php
class AdminController extends Controller
{
    public function __construct()
    {
        $this->middleware('auth');
    }

    public function index()
    {
        return User::all();
    }
}
```

## Symfony: missing security attribute

### Vulnerable

```php
class UserController extends AbstractController
{
    #[Route('/api/users', methods: ['GET'])]
    public function list(): JsonResponse
    {
        return $this->json($this->userRepo->findAll());
    }
}
```

### Safe

```php
use Symfony\Component\Security\Http\Attribute\IsGranted;

class UserController extends AbstractController
{
    #[Route('/api/users', methods: ['GET'])]
    #[IsGranted('ROLE_USER')]
    public function list(): JsonResponse
    {
        return $this->json($this->userRepo->findAll());
    }
}
```

Configure `access_control` in `security.yaml` for path-based
protection as a complement to per-action attributes.

## Hardcoded credentials

### Vulnerable

```php
public function authenticate(string $password): bool
{
    return $password === 'admin123';
}
```

### Safe

```php
public function authenticate(
    string $password,
    string $hash,
): bool {
    return Hash::check($password, $hash);
}
```

Laravel's `Hash::check()` uses bcrypt by default. Never store
or compare plaintext passwords.
