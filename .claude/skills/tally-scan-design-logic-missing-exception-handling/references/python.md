# Python missing exception handling patterns

Vulnerable-vs-safe snippets for Python auth middleware, decorators,
FastAPI dependencies, and assertion-based security checks.

## Django middleware

### Vulnerable

```python
class AuthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            user = User.objects.get(id=request.session.get("user_id"))
            request.user = user
        except User.DoesNotExist:
            pass  # Silent fail; request proceeds as anonymous
        return self.get_response(request)
```

### Safe

```python
class AuthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user_id = request.session.get("user_id")
        if user_id:
            try:
                request.user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                return HttpResponseForbidden("Session invalid")
        else:
            request.user = None
        return self.get_response(request)
```

When an auth check throws, return a 403 response or re-raise. Never
silently catch and continue.

## Flask before_request

### Vulnerable

```python
@app.before_request
def check_auth():
    try:
        token = request.headers.get("Authorization").split()[1]
        payload = jwt.decode(token, secret)
        g.user_id = payload["user_id"]
    except:
        pass  # Exception swallowed; handler executes anyway
```

### Safe

```python
@app.before_request
def check_auth():
    token = request.headers.get("Authorization")
    if not token:
        abort(401)
    try:
        payload = jwt.decode(token, secret)
        g.user_id = payload["user_id"]
    except jwt.DecodeError:
        abort(401)
```

Raise or abort on exception. Do not catch and ignore.

## FastAPI dependency with fail-open

### Vulnerable

```python
def get_current_user(token: str = Header(None)):
    try:
        payload = jwt.decode(token, secret)
        return User.get(payload["user_id"])
    except Exception:
        return None  # Dependency returns None; handler sees no user
```

```python
@app.get("/admin")
def admin_panel(user: Optional[User] = Depends(get_current_user)):
    if user is None:
        return {"error": "not authorized"}
    return {"data": "admin"}
```

The exception is caught and turned into None. The handler must check
for None, adding an extra layer of validation that is error-prone.

### Safe

```python
def get_current_user(token: str = Header(None)):
    if not token:
        raise HTTPException(status_code=401)
    try:
        payload = jwt.decode(token, secret)
        return User.get(payload["user_id"])
    except jwt.DecodeError:
        raise HTTPException(status_code=401)
```

Raise HTTPException directly in the dependency. FastAPI aborts the
request and returns the error response to the client.

## Generic decorator pattern

### Vulnerable

```python
def require_permission(permission):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                user = get_current_user()
                if not user.has_permission(permission):
                    raise PermissionDenied()
            except Exception:
                pass  # Exception caught; function still executes
            return func(*args, **kwargs)
        return wrapper
    return decorator

@require_permission("admin")
def delete_user(user_id):
    User.objects.get(id=user_id).delete()
```

### Safe

```python
def require_permission(permission):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            user = get_current_user()
            if not user or not user.has_permission(permission):
                raise PermissionDenied()
            return func(*args, **kwargs)
        return wrapper
    return decorator

@require_permission("admin")
def delete_user(user_id):
    User.objects.get(id=user_id).delete()
```

Let exceptions propagate from the permission check. Do not catch and
silently continue.

## Assert for security validation

### Vulnerable

```python
@app.get("/admin/users")
def list_users():
    user = get_current_user()
    assert user.is_admin  # Assertion stripped in -O mode
    return {"users": list_all_users()}
```

### Safe

```python
@app.get("/admin/users")
def list_users():
    user = get_current_user()
    if not user.is_admin:
        raise HTTPException(status_code=403)
    return {"users": list_all_users()}
```

Replace assertions with explicit raise statements. Assertions are
stripped in `-O` and `-OO` optimization modes, causing the security
check to vanish in production.

## Silent exception catch wrapping validation

### Vulnerable

```python
def apply_rate_limit(user_id):
    try:
        count = redis_conn.incr(f"user:{user_id}:requests")
        if count > 100:
            raise RateLimitExceeded()
    except Exception:
        pass  # Redis failure is silently ignored; request proceeds

@app.get("/api/endpoint")
def endpoint(user_id: int):
    apply_rate_limit(user_id)
    return {"result": "success"}
```

### Safe

```python
def apply_rate_limit(user_id):
    try:
        count = redis_conn.incr(f"user:{user_id}:requests")
        if count > 100:
            raise RateLimitExceeded()
    except RateLimitExceeded:
        raise HTTPException(status_code=429)
    except RedisConnectionError:
        raise HTTPException(
            status_code=503,
            detail="Service temporarily unavailable"
        )

@app.get("/api/endpoint")
def endpoint(user_id: int):
    apply_rate_limit(user_id)
    return {"result": "success"}
```

Catch only specific exceptions and handle them explicitly. For
connection failures, return a 5xx error instead of allowing the
request to proceed.
