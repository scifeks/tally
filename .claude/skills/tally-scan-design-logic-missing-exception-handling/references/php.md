# PHP missing exception handling patterns

Vulnerable-vs-safe snippets for PHP auth middleware (Laravel,
Symfony), security voters, and assertion-based validation.

## Laravel middleware

### Vulnerable

```php
class CheckAuth
{
    public function handle($request, Closure $next)
    {
        try {
            $user = User::findOrFail(
                $request->session()->get('user_id')
            );
            auth()->setUser($user);
        } catch (ModelNotFoundException $e) {
            // Silent catch; request proceeds as guest
        }
        return $next($request);
    }
}
```

### Safe

```php
class CheckAuth
{
    public function handle($request, Closure $next)
    {
        $userId = $request->session()->get('user_id');
        if (!$userId) {
            return response('Unauthorized', 401);
        }
        try {
            auth()->setUser(User::findOrFail($userId));
        } catch (ModelNotFoundException $e) {
            return response('Session invalid', 403);
        }
        return $next($request);
    }
}
```

In the catch block, return a 401 or 403 response. Never call
`$next($request)` when an auth check fails.

## Laravel Gate/Policy with fail-open

### Vulnerable

```php
class PostPolicy
{
    public function update(User $user, Post $post)
    {
        try {
            if ($post->owner_id !== $user->id) {
                throw new AuthorizationException('Not authorized');
            }
        } catch (AuthorizationException $e) {
            return false;  // Policy returns false; gate might not check
        }
        return true;
    }
}
```

### Safe

```php
class PostPolicy
{
    public function update(User $user, Post $post)
    {
        if ($post->owner_id !== $user->id) {
            return false;
        }
        return true;
    }
}
```

Remove the try/catch. Return false directly. The authorization gate
framework handles the denial.

## Symfony security voter

### Vulnerable

```php
class PostVoter extends Voter
{
    protected function voteOnAttribute(
        $attribute,
        $subject,
        TokenInterface $token
    ) {
        try {
            $user = $token->getUser();
            if (!$user instanceof User) {
                throw new AccessDeniedException();
            }
            if ($subject->getOwnerId() !== $user->getId()) {
                throw new AccessDeniedException();
            }
        } catch (AccessDeniedException $e) {
            return self::ACCESS_ABSTAIN;  // Abstain on exception
        }
        return self::ACCESS_GRANTED;
    }
}
```

### Safe

```php
class PostVoter extends Voter
{
    protected function voteOnAttribute(
        $attribute,
        $subject,
        TokenInterface $token
    ) {
        $user = $token->getUser();
        if (!$user instanceof User) {
            return self::ACCESS_DENIED;
        }
        if ($subject->getOwnerId() !== $user->getId()) {
            return self::ACCESS_DENIED;
        }
        return self::ACCESS_GRANTED;
    }
}
```

Return ACCESS_DENIED directly. Do not catch exceptions and return
ABSTAIN.

## Generic middleware with fail-open except

### Vulnerable

```php
class ApiTokenMiddleware
{
    public function handle($request, Closure $next)
    {
        try {
            $token = $request->header('X-API-Token');
            $this->validateToken($token);
        } catch (Exception $e) {
            // Exception silently caught; middleware continues
        }
        return $next($request);
    }

    private function validateToken($token)
    {
        if (!$token || !hash_equals($token, env('API_TOKEN'))) {
            throw new InvalidTokenException();
        }
    }
}
```

### Safe

```php
class ApiTokenMiddleware
{
    public function handle($request, Closure $next)
    {
        $token = $request->header('X-API-Token');
        try {
            $this->validateToken($token);
        } catch (InvalidTokenException $e) {
            return response('Unauthorized', 401);
        }
        return $next($request);
    }

    private function validateToken($token)
    {
        if (!$token || !hash_equals($token, env('API_TOKEN'))) {
            throw new InvalidTokenException();
        }
    }
}
```

In the catch block, return a 401 response instead of calling
`$next($request)`.

## Assertion for security validation

### Vulnerable

```php
public function deleteUser($userId)
{
    $user = $this->getCurrentUser();
    assert($user->isAdmin);  // Can be disabled via zend.assertions=-1
    $this->userRepository->delete($userId);
}
```

### Safe

```php
public function deleteUser($userId)
{
    $user = $this->getCurrentUser();
    if (!$user->isAdmin) {
        throw new ForbiddenException('Only admins can delete users');
    }
    $this->userRepository->delete($userId);
}
```

Use explicit if statements with exceptions. The `assert()` function can
be disabled via the `zend.assertions = -1` INI setting.

## Silent catch wrapping permission check

### Vulnerable

```php
class RateLimitMiddleware
{
    public function handle($request, Closure $next)
    {
        try {
            $key = 'user:' . auth()->id() . ':requests';
            $count = redis()->incr($key);
            if ($count > 100) {
                throw new RateLimitExceededException();
            }
        } catch (Exception $e) {
            // Redis connection fails; exception silently caught
        }
        return $next($request);
    }
}
```

### Safe

```php
class RateLimitMiddleware
{
    public function handle($request, Closure $next)
    {
        $key = 'user:' . auth()->id() . ':requests';
        try {
            $count = redis()->incr($key);
            if ($count > 100) {
                return response('Rate limit exceeded', 429);
            }
        } catch (ConnectionException $e) {
            return response('Service unavailable', 503);
        }
        return $next($request);
    }
}
```

Catch specific exceptions and return appropriate error codes. For
service unavailability, return 503 instead of allowing the request.

## WordPress permission check with fail-open

### Vulnerable

```php
function custom_api_handler() {
    try {
        if (!current_user_can('manage_options')) {
            throw new Exception('Not admin');
        }
        $this->deleteAllSettings();
    } catch (Exception $e) {
        // Exception caught; function continues
    }
    wp_send_json_success(['status' => 'deleted']);
}
```

### Safe

```php
function custom_api_handler() {
    if (!current_user_can('manage_options')) {
        wp_send_json_error(['error' => 'Unauthorized'], 403);
        return;
    }
    $this->deleteAllSettings();
    wp_send_json_success(['status' => 'deleted']);
}
```

Check permissions before the operation. Return an error response if the
check fails. Do not use try/catch to silence permission denials.
