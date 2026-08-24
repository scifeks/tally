# Python order-of-operations patterns

Vulnerable-vs-safe snippets for Python frameworks that the
`design_logic.order_of_operations` scanner recognizes.

## Django view decorator ordering

### Vulnerable

```python
from django.contrib.auth.decorators import login_required
from myapp.decorators import require_permission

@require_permission('admin')
@login_required
def admin_dashboard(request):
    return render(request, 'admin.html')
```

Django decorators execute bottom-up. `@login_required` runs first, then
`@require_permission`. But here, `@require_permission` is placed above
`@login_required`, which does not change execution order; the permission
check still runs before login is verified. The intent is unclear.

### Safe

```python
@login_required
@require_permission('admin')
def admin_dashboard(request):
    return render(request, 'admin.html')
```

Decorators execute bottom-up: `@require_permission` runs first, then
`@login_required`. The user is authenticated before permission is
checked. Clearer intent, correct order.

Alternatively, use a single decorator that combines both checks:

```python
def require_login_and_permission(permission):
    def decorator(view):
        @login_required
        def wrapper(request):
            if not request.user.has_perm(permission):
                raise PermissionDenied()
            return view(request)
        return wrapper
    return decorator

@require_login_and_permission('admin')
def admin_dashboard(request):
    return render(request, 'admin.html')
```

## Django before_request hook ordering

### Vulnerable

```python
@app.before_request
def check_authorization():
    if not current_user.has_permission('admin'):
        abort(403)

@app.before_request
def check_authentication():
    if not current_user.is_authenticated:
        abort(401)
```

The order of registration is ambiguous without reading the Flask docs.
If `check_authorization` runs first, an unauthenticated user bypasses
the auth check and reaches the permission check.

### Safe

```python
@app.before_request
def check_authentication():
    if not current_user.is_authenticated:
        abort(401)

@app.before_request
def check_authorization():
    if not current_user.has_permission('admin'):
        abort(403)
```

Flask executes `before_request` hooks in registration order. Register
authentication first, authorization second.

## FastAPI dependency ordering

### Vulnerable

```python
async def get_current_user(token: str = Depends(oauth2_scheme)):
    return decode_token(token)

async def get_admin(user = Depends(get_current_user)):
    if user.role != 'admin':
        raise HTTPException(status_code=403)
    return user

@app.get("/admin")
async def admin_panel(user=Depends(get_admin)):
    return {"message": "Welcome admin"}
```

This is actually correct: `get_admin` depends on `get_current_user`, so
FastAPI resolves `get_current_user` first. The intent is clear and the
order is enforced by the dependency graph.

### Vulnerable alternate (order not enforced)

```python
@app.get("/admin")
async def admin_panel(request: Request):
    admin = request.user.role == 'admin'
    if admin:
        token = request.headers.get('authorization')
        if not token:
            raise HTTPException(status_code=401)
    return {"message": "Authorized"}
```

Here, authorization is checked before the authorization header is
validated. An unauthenticated request might bypass the auth check
depending on the order of conditionals.

### Safe

```python
@app.get("/admin")
async def admin_panel(user=Depends(verify_token_and_user)):
    if not user or user.role != 'admin':
        raise HTTPException(status_code=403)
    return {"message": "Welcome admin"}

async def verify_token_and_user(token: str = Depends(oauth2_scheme)):
    user = decode_token(token)
    if not user:
        raise HTTPException(status_code=401)
    return user
```

Dependency injection enforces the order: `verify_token_and_user` must
complete and return a valid user before `admin_panel` runs. No request
can reach the endpoint without a valid token and user.

## Validation before persistence

### Vulnerable

```python
def create_user(name, email):
    user = User(name=name, email=email)
    session.add(user)
    session.commit()
    if not validate_email(email):
        raise ValueError("Invalid email")
    return user
```

The user is persisted to the database before the email is validated. An
invalid email reaches the database.

### Safe

```python
def create_user(name, email):
    if not validate_email(email):
        raise ValueError("Invalid email")
    user = User(name=name, email=email)
    session.add(user)
    session.commit()
    return user
```

Validation runs before persistence. Only valid data reaches the
database.

## Sanitization before logging

### Vulnerable

```python
import logging
logger = logging.getLogger(__name__)

def process_request(user_input):
    logger.info(f"Processing request: {user_input}")
    sanitized = sanitize(user_input)
    return sanitized
```

The raw user input is logged before sanitization. Sensitive data or
injection payloads are logged unsanitized.

### Safe

```python
def process_request(user_input):
    sanitized = sanitize(user_input)
    logger.info(f"Processing request: {sanitized}")
    return sanitized
```

Sanitization runs before logging. Only safe data reaches the logs.

## File write before path validation

### Vulnerable

```python
def save_file(filename, content):
    with open(f"/uploads/{filename}", 'w') as f:
        f.write(content)
    if not is_valid_filename(filename):
        raise ValueError("Invalid filename")
```

The file is written before the filename is validated. A path traversal
payload (e.g., `../../etc/passwd`) reaches the filesystem before
validation blocks it.

### Safe

```python
def save_file(filename, content):
    if not is_valid_filename(filename):
        raise ValueError("Invalid filename")
    with open(f"/uploads/{filename}", 'w') as f:
        f.write(content)
```

Filename validation runs before the write. Only safe paths reach the
filesystem.

## Rate limiting before expensive operation

### Vulnerable

```python
@app.post("/compute")
def compute(payload):
    result = expensive_calculation(payload)
    if user_requests_per_minute >= RATE_LIMIT:
        abort(429)
    return result
```

The expensive operation completes before the rate limit is checked. An
attacker can trigger expensive computations without limit until the
rate limit fires.

### Safe

```python
@app.post("/compute")
def compute(payload):
    if user_requests_per_minute >= RATE_LIMIT:
        abort(429)
    result = expensive_calculation(payload)
    return result
```

Rate limiting runs before the expensive operation. The operation does
not run if the rate limit is exceeded.

Alternatively, use a decorator:

```python
from ratelimit import limits, sleep_and_retry

@limits(calls=10, period=60)
@sleep_and_retry
@app.post("/compute")
def compute(payload):
    result = expensive_calculation(payload)
    return result
```
