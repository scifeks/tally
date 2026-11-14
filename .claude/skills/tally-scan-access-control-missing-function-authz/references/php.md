# PHP missing function-level authorization patterns

Vulnerable-vs-safe snippets for the PHP frameworks the
`access_control.missing_function_authz` scanner recognizes. When
multiple safe forms exist, the canonical one is shown first.

## Laravel

### Vulnerable

```php
// routes/web.php
Route::post('/users', [UserController::class, 'store']);

// app/Http/Controllers/UserController.php
public function store(Request $request)
{
    // No middleware applied; any user can create users
    $user = User::create([
        'email' => $request->input('email'),
    ]);
    return response()->json(['id' => $user->id]);
}
```

```php
// routes/web.php
Route::put('/users/{id}', [UserController::class, 'update']);
// No middleware; endpoint is unprotected

// app/Http/Controllers/UserController.php
public function update(Request $request, $id)
{
    // State-changing without auth check
    $user = User::find($id);
    $user->is_admin = $request->input('is_admin');
    $user->save();
    return response()->json(['status' => 'ok']);
}
```

### Safe

```php
// routes/web.php
Route::post('/users', [UserController::class, 'store'])
    ->middleware('auth');

// app/Http/Controllers/UserController.php
public function store(Request $request)
{
    // Auth verified by middleware
    $user = User::create([
        'email' => $request->input('email'),
    ]);
    return response()->json(['id' => $user->id]);
}
```

For role-based access, use gates or policies:

```php
// routes/web.php
Route::put('/users/{id}', [UserController::class, 'update'])
    ->middleware('can:update,user');

// app/Http/Controllers/UserController.php
public function update(Request $request, User $user)
{
    // Policy verified by middleware
    $user->is_admin = $request->input('is_admin');
    $user->save();
    return response()->json(['status' => 'ok']);
}

// app/Policies/UserPolicy.php
public function update(User $authUser, User $user)
{
    return $authUser->is_admin;
}
```

Alternatively, use `auth` middleware with inline authorization:

```php
public function update(Request $request, User $user)
{
    $this->authorize('update', $user);
    $user->is_admin = $request->input('is_admin');
    $user->save();
    return response()->json(['status' => 'ok']);
}
```

## Symfony

### Vulnerable

```php
// src/Controller/UserController.php
public function create(Request $request)
{
    // No #[IsGranted] attribute; endpoint is public
    $user = new User();
    $user->setEmail($request->request->get('email'));
    $entityManager = $this->getDoctrine()->getManager();
    $entityManager->persist($user);
    $entityManager->flush();
    return new JsonResponse(['id' => $user->getId()]);
}

public function update(Request $request, User $user)
{
    // State-changing without access control
    $user->setEmail($request->request->get('email'));
    $entityManager = $this->getDoctrine()->getManager();
    $entityManager->flush();
    return new JsonResponse(['status' => 'ok']);
}
```

### Safe

```php
use Symfony\Component\Security\Http\Attribute\IsGranted;
use Symfony\Component\Security\Core\Exception\AccessDeniedException;

public function create(Request $request)
{
    // Access control verified via attribute
    #[IsGranted('ROLE_USER')]
    public function create(Request $request)
    {
        $user = new User();
        $user->setEmail($request->request->get('email'));
        $entityManager = $this->getDoctrine()->getManager();
        $entityManager->persist($user);
        $entityManager->flush();
        return new JsonResponse(['id' => $user->getId()]);
    }
}

public function update(Request $request, User $user)
{
    #[IsGranted('ROLE_ADMIN')]
    public function update(Request $request, User $user)
    {
        $user->setEmail($request->request->get('email'));
        $entityManager = $this->getDoctrine()->getManager();
        $entityManager->flush();
        return new JsonResponse(['status' => 'ok']);
    }
}
```

For data-dependent access, use voters:

```php
#[IsGranted('EDIT_USER', 'user')]
public function update(Request $request, User $user)
{
    $user->setEmail($request->request->get('email'));
    $entityManager = $this->getDoctrine()->getManager();
    $entityManager->flush();
    return new JsonResponse(['status' => 'ok']);
}

// src/Security/Voter/UserVoter.php
public function vote(
    TokenInterface $token,
    mixed $subject,
    array $attributes
): int {
    if (!in_array('EDIT_USER', $attributes)) {
        return self::ABSTAIN;
    }
    if (!$subject instanceof User) {
        return self::ABSTAIN;
    }
    $user = $token->getUser();
    if (!$user instanceof User) {
        return self::DENY;
    }
    return ($user->getId() === $subject->getId() ||
        $user->hasRole('ROLE_ADMIN'))
        ? self::ALLOW
        : self::DENY;
}
```

## Raw PHP (native session)

### Vulnerable

```php
<?php
// No auth check; endpoint is public
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $user = User::findById($_POST['user_id']);
    $user->setEmail($_POST['email']);
    $user->save();
    echo json_encode(['status' => 'ok']);
}
?>
```

### Safe

```php
<?php
session_start();

// Auth check must come before state changes
if (!isset($_SESSION['user_id'])) {
    http_response_code(403);
    echo json_encode(['error' => 'Unauthorized']);
    exit;
}

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $user = User::findById($_POST['user_id']);
    $user->setEmail($_POST['email']);
    $user->save();
    echo json_encode(['status' => 'ok']);
}
?>
```

For role-based access:

```php
<?php
session_start();

if (!isset($_SESSION['user_id']) || $_SESSION['role'] !== 'admin') {
    http_response_code(403);
    echo json_encode(['error' => 'Forbidden']);
    exit;
}

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $user = User::findById($_POST['user_id']);
    $user->setEmail($_POST['email']);
    $user->save();
    echo json_encode(['status' => 'ok']);
}
?>
```
