# Python session management patterns

Vulnerable-vs-safe snippets for Flask and Django session handling
that the `authentication.session_management` scanner recognizes.

## Flask: session fixation

### Vulnerable

```python
@app.route("/login", methods=["POST"])
def login():
    user = authenticate(
        request.form["username"],
        request.form["password"],
    )
    if user:
        session["user_id"] = user.id
        return redirect("/dashboard")
```

### Safe

```python
@app.route("/login", methods=["POST"])
def login():
    user = authenticate(
        request.form["username"],
        request.form["password"],
    )
    if user:
        session.clear()
        session["user_id"] = user.id
        return redirect("/dashboard")
```

Flask has no `session.regenerate()` method. Calling
`session.clear()` before repopulating prevents fixation by
discarding any attacker-set session data.

## Django: session fixation

### Vulnerable

```python
def login_view(request):
    form = LoginForm(request.POST)
    if form.is_valid():
        user = form.get_user()
        request.session["user_id"] = user.pk
        return redirect("/dashboard")
```

### Safe

```python
from django.contrib.auth import login

def login_view(request):
    form = LoginForm(request.POST)
    if form.is_valid():
        user = form.get_user()
        login(request, user)
        return redirect("/dashboard")
```

`django.contrib.auth.login()` calls `request.session.cycle_key()`
automatically. If you must set session data manually, call
`request.session.cycle_key()` first.

## Flask: insecure cookie flags

### Vulnerable

```python
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ["SECRET_KEY"]
```

### Safe

```python
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ["SECRET_KEY"]
app.config["SESSION_COOKIE_SECURE"] = True
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
```

Omitting these flags leaves cookies vulnerable to interception
over HTTP, XSS-based theft, and cross-site request attachment.

## Django: insecure cookie flags

### Vulnerable

```python
# settings.py
SESSION_COOKIE_SECURE = False
SESSION_COOKIE_HTTPONLY = False
```

### Safe

```python
# settings.py
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 3600
```

`SESSION_COOKIE_AGE` defaults to two weeks (1209600 seconds).
Set it to the shortest acceptable window for the application.

## Django: excessive session timeout

### Vulnerable

```python
# settings.py
SESSION_COOKIE_AGE = 31536000  # one year
```

### Safe

```python
# settings.py
SESSION_COOKIE_AGE = 3600  # one hour
SESSION_SAVE_EVERY_REQUEST = True
```

Long-lived sessions increase the window for session hijacking.
`SESSION_SAVE_EVERY_REQUEST` refreshes the expiry on each
request, acting as an idle timeout.
