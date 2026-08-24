# PHP insufficient logging patterns

Vulnerable-vs-safe snippets for PHP auth handlers, middleware, admin
operations, and exception handling lacking audit trails.

## Laravel login controller without logging

### Vulnerable

```php
class LoginController extends Controller
{
    public function authenticate(Request $request)
    {
        $credentials = $request->validate([
            'email' => ['required', 'email'],
            'password' => ['required'],
        ]);

        if (Auth::attempt($credentials)) {
            $request->session()->regenerate();
            return redirect('/dashboard');
        }
        return back()->withErrors(['email' => 'Invalid credentials']);
    }
}
```

### Safe

```php
use Illuminate\Support\Facades\Log;

class LoginController extends Controller
{
    public function authenticate(Request $request)
    {
        $credentials = $request->validate([
            'email' => ['required', 'email'],
            'password' => ['required'],
        ]);

        if (Auth::attempt($credentials)) {
            $user = Auth::user();
            Log::info('User login successful', [
                'user_id' => $user->id,
                'email' => $user->email,
                'ip' => $request->ip(),
            ]);
            $request->session()->regenerate();
            return redirect('/dashboard');
        }
        Log::warning('User login failed', [
            'email' => $credentials['email'],
            'ip' => $request->ip(),
        ]);
        return back()->withErrors(['email' => 'Invalid credentials']);
    }
}
```

Log both successful and failed authentication attempts with user ID,
timestamp, and client IP.

## Laravel middleware silently catching auth

### Vulnerable

```php
class CheckApiToken
{
    public function handle($request, Closure $next)
    {
        try {
            $token = $request->header('X-API-Token');
            $this->validateToken($token);
        } catch (InvalidTokenException $e) {
            return $next($request);  // Request proceeds anyway
        }
        return $next($request);
    }

    private function validateToken($token)
    {
        if (!$token || !hash_equals($token, config('api.token'))) {
            throw new InvalidTokenException();
        }
    }
}
```

### Safe

```php
use Illuminate\Support\Facades\Log;

class CheckApiToken
{
    public function handle($request, Closure $next)
    {
        try {
            $token = $request->header('X-API-Token');
            $this->validateToken($token);
        } catch (InvalidTokenException $e) {
            Log::warning('Invalid API token provided', [
                'path' => $request->path(),
                'ip' => $request->ip(),
            ]);
            return response('Unauthorized', 401);
        }
        Log::info('API request authorized', [
            'path' => $request->path(),
            'ip' => $request->ip(),
        ]);
        return $next($request);
    }

    private function validateToken($token)
    {
        if (!$token || !hash_equals($token, config('api.token'))) {
            throw new InvalidTokenException();
        }
    }
}
```

Log all auth failures before denying access. Never catch and proceed
silently.

## Laravel authorization gate without logging

### Vulnerable

```php
class PostPolicy
{
    public function update(User $user, Post $post)
    {
        return $post->user_id === $user->id;
    }
}

public function updatePost(Post $post, Request $request)
{
    $this->authorize('update', $post);
    $post->update($request->all());
    return redirect('/posts/' . $post->id);
}
```

### Safe

```php
use Illuminate\Support\Facades\Log;

class PostPolicy
{
    public function update(User $user, Post $post)
    {
        $allowed = $post->user_id === $user->id;
        if (!$allowed) {
            Log::warning('Unauthorized post update attempt', [
                'user_id' => $user->id,
                'post_id' => $post->id,
            ]);
        }
        return $allowed;
    }
}

public function updatePost(Post $post, Request $request)
{
    $user = Auth::user();
    $this->authorize('update', $post);
    Log::info('Post updated', [
        'user_id' => $user->id,
        'post_id' => $post->id,
    ]);
    $post->update($request->all());
    return redirect('/posts/' . $post->id);
}
```

Log both authorization failures and approvals for sensitive operations.

## Symfony security voter without logging

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
                return self::ACCESS_DENIED;
            }
            if ($subject->getOwnerId() !== $user->getId()) {
                throw new AccessDeniedException();
            }
        } catch (AccessDeniedException $e) {
            return self::ACCESS_ABSTAIN;
        }
        return self::ACCESS_GRANTED;
    }
}
```

### Safe

```php
use Psr\Log\LoggerInterface;

class PostVoter extends Voter
{
    public function __construct(private LoggerInterface $logger) {}

    protected function voteOnAttribute(
        $attribute,
        $subject,
        TokenInterface $token
    ) {
        $user = $token->getUser();
        if (!$user instanceof User) {
            $this->logger->warning('Non-user access to post', [
                'resource' => 'post_' . $subject->getId(),
            ]);
            return self::ACCESS_DENIED;
        }
        if ($subject->getOwnerId() !== $user->getId()) {
            $this->logger->warning('Unauthorized post access', [
                'user_id' => $user->getId(),
                'post_id' => $subject->getId(),
            ]);
            return self::ACCESS_DENIED;
        }
        return self::ACCESS_GRANTED;
    }
}
```

Log permission denials with user identity and resource being accessed.

## Admin endpoint without action logging

### Vulnerable

```php
class UserController extends Controller
{
    public function store(Request $request)
    {
        $this->authorize('admin');
        $user = User::create($request->all());
        return redirect('/admin/users')->with('status', 'User created');
    }

    public function destroy(User $user)
    {
        $this->authorize('admin');
        $user->delete();
        return redirect('/admin/users')->with('status', 'User deleted');
    }
}
```

### Safe

```php
use Illuminate\Support\Facades\Log;

class UserController extends Controller
{
    public function store(Request $request)
    {
        $admin = Auth::user();
        $this->authorize('admin');
        $user = User::create($request->all());
        Log::info('User created by admin', [
            'admin_id' => $admin->id,
            'created_user_id' => $user->id,
            'email' => $user->email,
            'ip' => $request->ip(),
        ]);
        return redirect('/admin/users')->with('status', 'User created');
    }

    public function destroy(User $user)
    {
        $admin = Auth::user();
        $this->authorize('admin');
        Log::info('User deleted by admin', [
            'admin_id' => $admin->id,
            'deleted_user_id' => $user->id,
            'email' => $user->email,
            'ip' => $request->ip(),
        ]);
        $user->delete();
        return redirect('/admin/users')->with('status', 'User deleted');
    }
}
```

Log all admin state-changing operations with the acting admin's ID,
timestamp, and what changed.

## Password reset without audit trail

### Vulnerable

```php
class ResetPasswordController extends Controller
{
    public function sendResetLink(Request $request)
    {
        $request->validate(['email' => 'required|email']);
        Password::sendResetLink($request->only('email'));
        return back()->with('status', 'Password reset link sent!');
    }
}
```

### Safe

```php
use Illuminate\Support\Facades\Log;

class ResetPasswordController extends Controller
{
    public function sendResetLink(Request $request)
    {
        $email = $request->validate(['email' => 'required|email'])['email'];
        $user = User::where('email', $email)->first();
        if ($user) {
            Log::info('Password reset requested', [
                'user_id' => $user->id,
                'email' => $email,
                'ip' => $request->ip(),
            ]);
        } else {
            Log::warning('Password reset requested for unknown email', [
                'email' => $email,
                'ip' => $request->ip(),
            ]);
        }
        Password::sendResetLink(['email' => $email]);
        return back()->with('status', 'Password reset link sent!');
    }
}
```

Log password reset requests (success and failure) with user ID and
client IP.

## Permission role change without logging

### Vulnerable

```php
public function assignRole(User $user, $role)
{
    $user->assignRole($role);
    return redirect()->back();
}

public function removeRole(User $user, $role)
{
    $user->removeRole($role);
    return redirect()->back();
}
```

### Safe

```php
use Illuminate\Support\Facades\Log;

public function assignRole(User $user, $role)
{
    $admin = Auth::user();
    Log::info('Role assigned', [
        'admin_id' => $admin->id,
        'target_user_id' => $user->id,
        'role' => $role,
        'ip' => request()->ip(),
    ]);
    $user->assignRole($role);
    return redirect()->back();
}

public function removeRole(User $user, $role)
{
    $admin = Auth::user();
    Log::info('Role removed', [
        'admin_id' => $admin->id,
        'target_user_id' => $user->id,
        'role' => $role,
        'ip' => request()->ip(),
    ]);
    $user->removeRole($role);
    return redirect()->back();
}
```

Log all permission and role changes with who made the change, what
changed, and when.

## Exception caught without logging in security context

### Vulnerable

```php
public function validateSignature($payload, $signature)
{
    try {
        $expectedSig = hash_hmac('sha256', $payload, secret());
        if (!hash_equals($expectedSig, $signature)) {
            throw new InvalidSignatureException();
        }
        return true;
    } catch (InvalidSignatureException $e) {
        return false;  // Silent fail
    }
}
```

### Safe

```php
use Psr\Log\LoggerInterface;

public function validateSignature(
    $payload,
    $signature,
    LoggerInterface $logger
) {
    try {
        $expectedSig = hash_hmac('sha256', $payload, secret());
        if (!hash_equals($expectedSig, $signature)) {
            throw new InvalidSignatureException();
        }
        return true;
    } catch (InvalidSignatureException $e) {
        $logger->warning('Invalid signature provided', [
            'payload_hash' => hash('sha256', $payload),
        ]);
        return false;
    }
}
```

Log all signature validation failures with details to aid
investigation.
