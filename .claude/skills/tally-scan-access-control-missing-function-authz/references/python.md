# Python missing function-level authorization patterns

Vulnerable-vs-safe snippets for the Python frameworks the
`access_control.missing_function_authz` scanner recognizes. When
multiple safe forms exist, the canonical one is shown first.

## Django

### Vulnerable

```python
class UserListView(View):
    def post(self, request):
        # No @login_required decorator on the view or method
        user = User.objects.create(
            email=request.POST.get("email"),
        )
        return JsonResponse({"id": user.id})
```

```python
@csrf_exempt
def update_user(request):
    # State-changing handler with no auth check
    if request.method == "POST":
        user = User.objects.get(id=request.POST.get("user_id"))
        user.is_admin = request.POST.get("is_admin")
        user.save()
        return JsonResponse({"status": "ok"})
```

### Safe

```python
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin

# Decorator on function-based view
@login_required
def update_user(request):
    if request.method == "POST":
        user = User.objects.get(id=request.POST.get("user_id"))
        user.is_admin = request.POST.get("is_admin")
        user.save()
        return JsonResponse({"status": "ok"})

# Mixin on class-based view
class UserListView(LoginRequiredMixin, View):
    def post(self, request):
        user = User.objects.create(
            email=request.POST.get("email"),
        )
        return JsonResponse({"id": user.id})
```

For permission-specific actions, use `@permission_required`:

```python
from django.contrib.auth.decorators import permission_required

@permission_required("app.add_user")
def create_user(request):
    if request.method == "POST":
        user = User.objects.create(email=request.POST.get("email"))
        return JsonResponse({"id": user.id})
```

## Django REST Framework

### Vulnerable

```python
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny

class UserListView(APIView):
    permission_classes = []  # No auth required
    def post(self, request):
        user = User.objects.create(email=request.data.get("email"))
        return Response({"id": user.id})
```

```python
from rest_framework import viewsets

class UserViewSet(viewsets.ModelViewSet):
    # No permission_classes defined; defaults to AllowAny
    queryset = User.objects.all()
    serializer_class = UserSerializer
```

### Safe

```python
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

class UserListView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        user = User.objects.create(email=request.data.get("email"))
        return Response({"id": user.id})
```

```python
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated, IsAdminUser

class UserViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsAdminUser]
    queryset = User.objects.all()
    serializer_class = UserSerializer

    def create(self, request, *args, **kwargs):
        # Both viewset and method have permission checks
        return super().create(request, *args, **kwargs)
```

For custom permissions, define a Permission class:

```python
from rest_framework.permissions import BasePermission

class CanEditUser(BasePermission):
    def has_object_permission(self, request, view, obj):
        return obj.owner == request.user or request.user.is_staff

class UserViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, CanEditUser]
    queryset = User.objects.all()
```

## FastAPI

### Vulnerable

```python
from fastapi import FastAPI

app = FastAPI()

@app.post("/users")
async def create_user(email: str):
    # No auth dependency; endpoint is public
    user = User.objects.create(email=email)
    return {"id": user.id}

@app.put("/users/{user_id}")
async def update_user(user_id: int, data: dict):
    # No security scheme; state-changing without auth
    user = User.objects.get(id=user_id)
    user.email = data.get("email")
    user.save()
    return {"status": "ok"}
```

### Safe

```python
from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import HTTPBearer

app = FastAPI()
security = HTTPBearer()

async def get_current_user(credentials = Depends(security)):
    token = credentials.credentials
    try:
        user = verify_token(token)
        if not user:
            raise HTTPException(status_code=403)
        return user
    except Exception:
        raise HTTPException(status_code=403)

@app.post("/users")
async def create_user(
    email: str,
    current_user = Depends(get_current_user),
):
    # Auth verified via Depends
    user = User.objects.create(email=email)
    return {"id": user.id}

@app.put("/users/{user_id}")
async def update_user(
    user_id: int,
    data: dict,
    current_user = Depends(get_current_user),
):
    user = User.objects.get(id=user_id)
    user.email = data.get("email")
    user.save()
    return {"status": "ok"}
```

## Flask-Login

### Vulnerable

```python
from flask import Flask, request

app = Flask(__name__)

@app.route("/update_profile", methods=["POST"])
def update_profile():
    # No @login_required; state-changing endpoint is public
    user = User.query.get(request.form.get("user_id"))
    user.email = request.form.get("email")
    user.save()
    return {"status": "ok"}
```

### Safe

```python
from flask import Flask, request
from flask_login import login_required

app = Flask(__name__)

@app.route("/update_profile", methods=["POST"])
@login_required
def update_profile():
    user = User.query.get(request.form.get("user_id"))
    user.email = request.form.get("email")
    user.save()
    return {"status": "ok"}
```

For role-based access, create a custom decorator:

```python
from flask_login import login_required, current_user
from functools import wraps

def role_required(role):
    def decorator(fn):
        @wraps(fn)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role != role:
                abort(403)
            return fn(*args, **kwargs)
        return wrapped
    return decorator

@app.route("/admin/users", methods=["POST"])
@role_required("admin")
def create_user():
    user = User.query.create(email=request.form.get("email"))
    return {"id": user.id}
```
