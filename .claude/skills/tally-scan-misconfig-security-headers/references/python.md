# Python missing security headers patterns

Vulnerable-vs-safe snippets for Python web frameworks the
`misconfig.security_headers` scanner recognizes. When multiple safe forms
exist, the canonical one is shown first.

## Django settings

### Vulnerable

```python
# settings.py: missing or incorrect security header configuration
DEBUG = True
SECURE_HSTS_SECONDS = 0
SECURE_CONTENT_TYPE_NOSNIFF = False
# X_FRAME_OPTIONS not set
# SECURE_REFERRER_POLICY not set
```

### Safe

```python
# settings.py: proper security header configuration
DEBUG = False
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'
SECURE_SSL_REDIRECT = True
```

Set SECURE_HSTS_SECONDS to at least 31536000 (one year) to enable HSTS.
Set SECURE_CONTENT_TYPE_NOSNIFF to True to prevent MIME sniffing. Set
X_FRAME_OPTIONS to DENY to prevent clickjacking. Configure
SECURE_REFERRER_POLICY to control referrer leakage.

## Flask without Talisman

### Vulnerable

```python
from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/api/user')
def get_user():
    return jsonify({'id': 1, 'name': 'Alice'})

if __name__ == '__main__':
    app.run()
```

### Safe

```python
from flask import Flask, jsonify
from flask_talisman import Talisman

app = Flask(__name__)
Talisman(app, force_https=True, strict_transport_security_max_age=31536000)

@app.route('/api/user')
def get_user():
    return jsonify({'id': 1, 'name': 'Alice'})

if __name__ == '__main__':
    app.run()
```

Install Flask-Talisman and call Talisman(app) to automatically inject
security headers on all responses. Talisman sets X-Content-Type-Options,
X-Frame-Options, and Strict-Transport-Security by default.

## Starlette without middleware

### Vulnerable

```python
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

async def homepage(request):
    return JSONResponse({'message': 'Hello'})

app = Starlette(routes=[Route('/', homepage)])
```

### Safe

```python
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Route

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Strict-Transport-Security'] = (
            'max-age=31536000; includeSubDomains'
        )
        response.headers['Referrer-Policy'] = (
            'strict-origin-when-cross-origin'
        )
        return response

async def homepage(request):
    return JSONResponse({'message': 'Hello'})

middleware = [Middleware(SecurityHeadersMiddleware)]
app = Starlette(
    routes=[Route('/', homepage)],
    middleware=middleware
)
```

Create a middleware that injects security headers on every response.
Apply it globally to the Starlette application via the middleware list.

## FastAPI without middleware

### Vulnerable

```python
from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI()

@app.get('/api/items')
async def list_items():
    return JSONResponse({'items': []})
```

### Safe

```python
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Strict-Transport-Security'] = (
            'max-age=31536000; includeSubDomains'
        )
        response.headers['Referrer-Policy'] = (
            'strict-origin-when-cross-origin'
        )
        return response

app = FastAPI()
app.add_middleware(SecurityHeadersMiddleware)

@app.get('/api/items')
async def list_items():
    return JSONResponse({'items': []})
```

Create a Starlette middleware and add it to the FastAPI application using
add_middleware(). The middleware runs on every request and injects security
headers into the response.
