# Python authentication patterns

Vulnerable-vs-safe snippets for Flask, Django, FastAPI, and DRF
that the `authentication.weak_or_missing_authn` scanner recognizes.

## Flask: missing @login_required

### Vulnerable

```python
@app.route("/api/users/<int:user_id>")
def get_user(user_id):
    user = User.query.get_or_404(user_id)
    return jsonify(user.to_dict())
```

### Safe

```python
from flask_login import login_required

@app.route("/api/users/<int:user_id>")
@login_required
def get_user(user_id):
    user = User.query.get_or_404(user_id)
    return jsonify(user.to_dict())
```

## Django: missing @login_required

### Vulnerable

```python
def user_profile(request, user_id):
    user = get_object_or_404(User, pk=user_id)
    return render(request, "profile.html", {"user": user})
```

### Safe

```python
from django.contrib.auth.decorators import login_required

@login_required
def user_profile(request, user_id):
    user = get_object_or_404(User, pk=user_id)
    return render(request, "profile.html", {"user": user})
```

For class-based views, use `LoginRequiredMixin` as the first
base class.

## FastAPI: missing auth dependency

### Vulnerable

```python
@app.get("/api/users/{user_id}")
async def get_user(user_id: int):
    return await user_service.get(user_id)
```

### Safe

```python
from fastapi import Depends

@app.get("/api/users/{user_id}")
async def get_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
):
    return await user_service.get(user_id)
```

## Django REST framework: missing permission

### Vulnerable

```python
class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
```

### Safe

```python
from rest_framework.permissions import IsAuthenticated

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
```

Set `DEFAULT_PERMISSION_CLASSES` in `REST_FRAMEWORK` settings
for global protection.

## Hardcoded credentials

### Vulnerable

```python
def authenticate(username, password):
    if username == "admin" and password == "admin123":
        return True
    return False
```

### Safe

```python
from werkzeug.security import check_password_hash

def authenticate(username, password):
    user = User.query.filter_by(username=username).first()
    if user and check_password_hash(user.password_hash, password):
        return user
    return None
```

Never compare plaintext passwords. Use bcrypt, argon2, or
`werkzeug.security` for hash-based comparison.
