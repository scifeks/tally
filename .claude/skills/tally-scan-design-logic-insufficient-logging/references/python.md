# Python insufficient logging patterns

Vulnerable-vs-safe snippets for Python auth handlers, middleware,
decorators, and admin operations lacking audit trails.

## Django login view without logging

### Vulnerable

```python
def login_view(request):
    username = request.POST.get("username")
    password = request.POST.get("password")
    user = authenticate(username=username, password=password)
    if user:
        login(request, user)
        return redirect("/dashboard")
    else:
        return render(request, "login.html", {"error": "Invalid"})
```

### Safe

```python
import logging

logger = logging.getLogger(__name__)

def login_view(request):
    username = request.POST.get("username")
    password = request.POST.get("password")
    user = authenticate(username=username, password=password)
    if user:
        login(request, user)
        logger.info(
            "User login successful",
            extra={
                "user_id": user.id,
                "username": username,
                "ip": get_client_ip(request),
            },
        )
        return redirect("/dashboard")
    else:
        logger.warning(
            "User login failed",
            extra={
                "username": username,
                "ip": get_client_ip(request),
            },
        )
        return render(request, "login.html", {"error": "Invalid"})
```

Log both successful and failed login attempts with timestamp, username,
and client IP.

## Flask auth decorator without logging

### Vulnerable

```python
def require_auth(func):
    @wraps(func)
    def decorator(*args, **kwargs):
        token = request.headers.get("Authorization")
        if not token or not verify_token(token):
            return {"error": "Unauthorized"}, 401
        return func(*args, **kwargs)
    return decorator

@app.route("/api/admin/users", methods=["DELETE"])
@require_auth
def delete_user():
    user_id = request.json.get("user_id")
    User.query.filter_by(id=user_id).delete()
    db.session.commit()
    return {"status": "deleted"}
```

### Safe

```python
import logging

logger = logging.getLogger(__name__)

def require_auth(func):
    @wraps(func)
    def decorator(*args, **kwargs):
        token = request.headers.get("Authorization")
        if not token or not verify_token(token):
            logger.warning(
                "Unauthorized API access attempt",
                extra={"path": request.path, "ip": request.remote_addr},
            )
            return {"error": "Unauthorized"}, 401
        user = get_user_from_token(token)
        return func(*args, **kwargs)
    return decorator

@app.route("/api/admin/users", methods=["DELETE"])
@require_auth
def delete_user():
    user = get_user_from_token(request.headers.get("Authorization"))
    user_id = request.json.get("user_id")
    logger.info(
        "User deleted by admin",
        extra={
            "admin_id": user.id,
            "deleted_user_id": user_id,
            "ip": request.remote_addr,
        },
    )
    User.query.filter_by(id=user_id).delete()
    db.session.commit()
    return {"status": "deleted"}
```

Log auth denials and all admin actions with user identity, timestamp,
and action details.

## FastAPI dependency with exception not logged

### Vulnerable

```python
from fastapi import Depends, HTTPException

def get_current_user(token: str = Header(None)):
    try:
        if not token:
            raise HTTPException(status_code=401)
        payload = jwt.decode(token, SECRET, algorithms=["HS256"])
        return User.get(payload["user_id"])
    except jwt.DecodeError:
        raise HTTPException(status_code=401)

@app.get("/admin/settings")
def admin_settings(user: User = Depends(get_current_user)):
    if not user.is_admin:
        return {"error": "Not admin"}
    return {"settings": {...}}
```

### Safe

```python
import logging
from fastapi import Depends, HTTPException

logger = logging.getLogger(__name__)

def get_current_user(token: str = Header(None)):
    try:
        if not token:
            logger.warning("API access without token")
            raise HTTPException(status_code=401)
        payload = jwt.decode(token, SECRET, algorithms=["HS256"])
        user = User.get(payload["user_id"])
        return user
    except jwt.DecodeError:
        logger.warning("Invalid token provided")
        raise HTTPException(status_code=401)

@app.get("/admin/settings")
def admin_settings(user: User = Depends(get_current_user)):
    if not user.is_admin:
        logger.warning(
            "Non-admin access to admin endpoint",
            extra={"user_id": user.id, "path": "/admin/settings"},
        )
        return {"error": "Not admin"}
    logger.info("Admin settings accessed", extra={"admin_id": user.id})
    return {"settings": {...}}
```

Log all auth failures and all access to admin endpoints, including
denials.

## Permission check without logging

### Vulnerable

```python
def update_post(post_id: int, data: dict):
    post = Post.get_by_id(post_id)
    if post.author_id != current_user.id:
        raise PermissionDenied()
    post.update(data)
    return post
```

### Safe

```python
import logging

logger = logging.getLogger(__name__)

def update_post(post_id: int, data: dict):
    post = Post.get_by_id(post_id)
    if post.author_id != current_user.id:
        logger.warning(
            "Unauthorized post access",
            extra={
                "user_id": current_user.id,
                "post_id": post_id,
                "action": "update",
            },
        )
        raise PermissionDenied()
    logger.info(
        "Post updated",
        extra={
            "user_id": current_user.id,
            "post_id": post_id,
        },
    )
    post.update(data)
    return post
```

Log both permission denials and approvals for sensitive data access.

## Password reset without audit trail

### Vulnerable

```python
@app.post("/api/password-reset")
def reset_password():
    email = request.json.get("email")
    user = User.query.filter_by(email=email).first()
    if user:
        token = generate_reset_token(user.id)
        send_reset_email(user.email, token)
    return {"status": "Check your email"}
```

### Safe

```python
import logging

logger = logging.getLogger(__name__)

@app.post("/api/password-reset")
def reset_password():
    email = request.json.get("email")
    user = User.query.filter_by(email=email).first()
    if user:
        logger.info(
            "Password reset requested",
            extra={
                "user_id": user.id,
                "email": email,
                "ip": request.remote_addr,
            },
        )
        token = generate_reset_token(user.id)
        send_reset_email(user.email, token)
    else:
        logger.warning(
            "Password reset requested for unknown email",
            extra={"email": email, "ip": request.remote_addr},
        )
    return {"status": "Check your email"}
```

Log all password reset requests (success and failure) with user ID,
timestamp, and client IP.

## Exception silently caught without logging

### Vulnerable

```python
@app.before_request
def check_rate_limit():
    try:
        user_id = get_current_user_id()
        key = f"rate_limit:{user_id}"
        count = redis_conn.incr(key)
        if count > 100:
            raise RateLimitExceeded()
    except Exception:
        pass  # Silent fail; request proceeds
```

### Safe

```python
import logging

logger = logging.getLogger(__name__)

@app.before_request
def check_rate_limit():
    try:
        user_id = get_current_user_id()
        key = f"rate_limit:{user_id}"
        count = redis_conn.incr(key)
        if count > 100:
            logger.warning(
                "Rate limit exceeded",
                extra={"user_id": user_id, "count": count},
            )
            raise RateLimitExceeded()
    except RateLimitExceeded:
        return {"error": "Too many requests"}, 429
    except RedisConnectionError:
        logger.error(
            "Rate limiter backend unavailable",
            exc_info=True,
        )
        return {"error": "Service temporarily unavailable"}, 503
```

Log all security failures explicitly, including connection errors. Do
not silently swallow exceptions.

## Admin user creation without logging

### Vulnerable

```python
@app.post("/admin/users")
@require_admin
def create_user():
    data = request.json
    user = User(
        email=data["email"],
        username=data["username"],
        is_admin=data.get("is_admin", False),
    )
    db.session.add(user)
    db.session.commit()
    return {"id": user.id}
```

### Safe

```python
import logging

logger = logging.getLogger(__name__)

@app.post("/admin/users")
@require_admin
def create_user():
    admin = get_current_user()
    data = request.json
    user = User(
        email=data["email"],
        username=data["username"],
        is_admin=data.get("is_admin", False),
    )
    db.session.add(user)
    db.session.commit()
    logger.info(
        "User created by admin",
        extra={
            "admin_id": admin.id,
            "created_user_id": user.id,
            "email": user.email,
            "is_admin": user.is_admin,
            "ip": request.remote_addr,
        },
    )
    return {"id": user.id}
```

Log all user creation and modification with the acting admin's ID,
timestamp, and what was changed.
