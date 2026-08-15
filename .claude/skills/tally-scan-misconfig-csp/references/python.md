# Python CSP misconfiguration patterns

Vulnerable-vs-safe snippets for Python web frameworks the `misconfig.csp`
scanner recognizes. When multiple safe forms exist, the canonical one is
shown first.

## Django CSP middleware

### Vulnerable

```python
# settings.py
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.middleware.common.CommonMiddleware',
]

# No CSP middleware is registered
```

### Safe

```python
# settings.py
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'csp.middleware.CSPMiddleware',
    'django.middleware.common.CommonMiddleware',
]

CSP_DEFAULT_SRC = ("'self'",)
CSP_SCRIPT_SRC = ("'self'", "cdn.example.com")
CSP_STYLE_SRC = ("'self'", "fonts.googleapis.com")
```

Register the `csp.middleware.CSPMiddleware` from the `django-csp` package in
the `MIDDLEWARE` list. Configure `CSP_DEFAULT_SRC` to restrict sources to
`'self'` and add specific directives for scripts and styles.

## Django CSP permissive

### Vulnerable

```python
# settings.py
CSP_DEFAULT_SRC = ("*",)
CSP_SCRIPT_SRC = ("*", "'unsafe-inline'")
CSP_STYLE_SRC = ("*", "'unsafe-eval'")
```

### Safe

```python
# settings.py
CSP_DEFAULT_SRC = ("'self'",)
CSP_SCRIPT_SRC = ("'self'",)
CSP_STYLE_SRC = ("'self'", "fonts.googleapis.com")
```

Replace wildcard sources with `'self'` and add explicit trusted origins only
for external resources required by the application.

## Flask-Talisman

### Vulnerable

```python
from flask_talisman import Talisman

app = Flask(__name__)
Talisman(app, content_security_policy=False)

# CSP is disabled entirely
```

### Safe

```python
from flask_talisman import Talisman

app = Flask(__name__)
csp = {
    'default-src': "'self'",
    'script-src': ["'self'", "cdn.example.com"],
    'style-src': ["'self'", "fonts.googleapis.com"],
}
Talisman(app, content_security_policy=csp)
```

Pass a restrictive `content_security_policy` dict to `Talisman()`. Set
`default-src` to `'self'` and add specific directives for scripts and styles
as needed.

## Flask-Talisman permissive

### Vulnerable

```python
from flask_talisman import Talisman

app = Flask(__name__)
csp = {
    'default-src': "*",
    'script-src': ["*", "'unsafe-inline'"],
}
Talisman(app, content_security_policy=csp)
```

### Safe

```python
from flask_talisman import Talisman

app = Flask(__name__)
csp = {
    'default-src': "'self'",
    'script-src': ["'self'"],
    'style-src': ["'self'", "https://fonts.googleapis.com"],
}
Talisman(app, content_security_policy=csp)
```

Replace wildcard sources with `'self'`. Remove `'unsafe-inline'` and
`'unsafe-eval'` unless the application requires inline scripts or styles, in
which case use a nonce-based policy instead.

## Starlette middleware

### Vulnerable

```python
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware

app = Starlette()

# No CSP header middleware is registered
# Or middleware that sets an empty or permissive CSP

async def add_csp_header(request, call_next):
    response = await call_next(request)
    response.headers['Content-Security-Policy'] = '*'
    return response

app.add_middleware(BaseHTTPMiddleware, dispatch=add_csp_header)
```

### Safe

```python
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware

app = Starlette()

async def add_csp_header(request, call_next):
    response = await call_next(request)
    csp = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' https://fonts.googleapis.com"
    )
    response.headers['Content-Security-Policy'] = csp
    return response

app.add_middleware(BaseHTTPMiddleware, dispatch=add_csp_header)
```

Set a restrictive CSP header with `default-src 'self'` and add specific
directives for scripts and styles. Avoid wildcards and unsafe directives.
