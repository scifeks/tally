# Python CSRF patterns

Vulnerable-vs-safe snippets for the Python web frameworks the
`access_control.csrf` scanner recognizes. When multiple safe forms exist,
the canonical one is shown first.

## Django

### Vulnerable

```python
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse

@csrf_exempt
def update_user(request):
    if request.method == "POST":
        user.name = request.POST.get("name")
        user.save()
        return HttpResponse("Updated")
```

```python
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.urls import path

class UpdateUserView(View):
    def post(self, request):
        user.name = request.POST.get("name")
        user.save()
        return HttpResponse("Updated")

urlpatterns = [
    path("user/update/", csrf_exempt(UpdateUserView.as_view())),
]
```

### Safe

```python
from django.http import HttpResponse

def update_user(request):
    if request.method == "POST":
        user.name = request.POST.get("name")
        user.save()
        return HttpResponse("Updated")
```

Django's `CsrfViewMiddleware` is enabled by default and validates the
CSRF token on POST/PUT/DELETE requests. The middleware expects a token
in the request body (for forms) or in the `X-CSRFToken` header (for
AJAX). Do not use `@csrf_exempt` unless the view is intentionally safe
(e.g. a webhook with its own authentication).

For class-based views, CSRF protection is automatic:

```python
from django.views import View
from django.http import HttpResponse

class UpdateUserView(View):
    def post(self, request):
        user.name = request.POST.get("name")
        user.save()
        return HttpResponse("Updated")

urlpatterns = [
    path("user/update/", UpdateUserView.as_view()),
]
```

## Flask with Flask-WTF

### Vulnerable

```python
from flask import Flask, request

app = Flask(__name__)

@app.route("/user/update", methods=["POST"])
def update_user():
    user.name = request.form.get("name")
    user.save()
    return "Updated"
```

### Safe

```python
from flask import Flask, request, render_template
from flask_wtf.csrf import CSRFProtect

app = Flask(__name__)
app.config["SECRET_KEY"] = "your-secret-key"
csrf = CSRFProtect(app)

@app.route("/user", methods=["GET"])
def edit_user():
    return render_template("edit.html")

@app.route("/user/update", methods=["POST"])
def update_user():
    user.name = request.form.get("name")
    user.save()
    return "Updated"
```

In the Jinja2 template:

```html
<form method="post" action="/user/update">
    {{ csrf_token() }}
    <input type="text" name="name">
    <input type="submit">
</form>
```

Initialize `CSRFProtect(app)` at startup. The protection is applied to
all POST/PUT/DELETE routes. Include `{{ csrf_token() }}` in HTML forms
or pass the token in the `X-CSRFToken` header for AJAX.

## Django REST Framework (DRF)

### Vulnerable

```python
from rest_framework.views import APIView
from rest_framework.response import Response
from django.views.decorators.csrf import csrf_exempt

class UpdateUserView(APIView):
    @csrf_exempt
    def post(self, request):
        user.name = request.data.get("name")
        user.save()
        return Response({"status": "ok"})
```

### Safe

```python
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.authentication import SessionAuthentication

class UpdateUserView(APIView):
    authentication_classes = [SessionAuthentication]

    def post(self, request):
        user.name = request.data.get("name")
        user.save()
        return Response({"status": "ok"})
```

DRF enforces CSRF checks for views using `SessionAuthentication`. Do not
use `@csrf_exempt` on DRF views. If you must exempt a view, use a
different authentication method (e.g. token-based) that does not require
CSRF.

## FastAPI with cookie-based sessions

### Vulnerable

```python
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

app = FastAPI()

@app.post("/user/update")
def update_user(request: Request):
    user.name = request.form().get("name")
    user.save()
    return {"status": "ok"}
```

### Safe

```python
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import secrets

app = FastAPI()
tokens = {}

@app.get("/user")
def edit_user():
    token = secrets.token_hex(32)
    tokens[token] = True
    return HTMLResponse(f"""
        <form method="post" action="/user/update">
            <input type="hidden" name="csrf_token" value="{token}">
            <input type="text" name="name">
            <input type="submit">
        </form>
    """)

@app.post("/user/update")
def update_user(request: Request):
    token = request.form().get("csrf_token")
    if token not in tokens:
        raise HTTPException(status_code=403, detail="Invalid token")
    user.name = request.form().get("name")
    user.save()
    del tokens[token]
    return {"status": "ok"}
```

FastAPI does not provide built-in CSRF protection for cookie-based
sessions. Implement manual validation: generate a unique token on GET,
require it in POST, and validate it server-side using `secrets` or a
dedicated library.
