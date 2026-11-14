# Python CORS misconfiguration patterns

Vulnerable-vs-safe snippets for Python web frameworks the `misconfig.cors`
scanner recognizes. When multiple safe forms exist, the canonical one is
shown first.

## django-cors-headers

### Vulnerable

```python
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True
```

```python
CORS_ORIGIN_WHITELIST = [
    "*",
]
CORS_ALLOW_CREDENTIALS = True
```

### Safe

```python
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = [
    "https://app.example.com",
    "https://trusted-partner.example.com",
]
CORS_ALLOW_CREDENTIALS = True
```

Set `CORS_ALLOW_ALL_ORIGINS = False` and list specific trusted origins in
`CORS_ALLOWED_ORIGINS`. Never combine wildcard origin with
`CORS_ALLOW_CREDENTIALS = True`.

## Flask-CORS

### Vulnerable

```python
from flask_cors import CORS
app = Flask(__name__)
CORS(app, origins="*", supports_credentials=True)
```

```python
CORS(app, origins=["*"], supports_credentials=True)
```

### Safe

```python
from flask_cors import CORS
app = Flask(__name__)
CORS(app, origins=["https://app.example.com"],
     supports_credentials=True)
```

Pass an explicit origins list to the CORS function. Validate origins against
a trusted allowlist rather than permitting any origin.

## Starlette / FastAPI CORSMiddleware

### Vulnerable

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
)
```

### Safe

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://app.example.com"],
    allow_credentials=True,
)
```

Provide an explicit list of allowed origins instead of wildcard. When
credentials are enabled, origins must be enumerated explicitly, not
wildcarded.

## Manual origin reflection

### Vulnerable

```python
from flask import Flask, request

app = Flask(__name__)

@app.route('/api/data')
def get_data():
    response.headers['Access-Control-Allow-Origin'] = \
        request.headers.get('Origin')
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    return jsonify(data)
```

### Safe

```python
from flask import Flask, request

ALLOWED_ORIGINS = [
    "https://app.example.com",
    "https://trusted-partner.example.com",
]

app = Flask(__name__)

@app.route('/api/data')
def get_data():
    origin = request.headers.get('Origin')
    if origin in ALLOWED_ORIGINS:
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Credentials'] = 'true'
    return jsonify(data)
```

Validate the Origin header against an allowlist of trusted domains before
reflecting it into the Access-Control-Allow-Origin response header. Never
reflect an unvalidated origin.
