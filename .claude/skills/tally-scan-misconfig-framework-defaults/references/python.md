# Python framework defaults patterns

Vulnerable-vs-safe snippets for Python framework default settings the
`misconfig.framework_defaults` scanner recognizes. When multiple safe
forms exist, the canonical one is shown first.

## Django DEBUG setting

### Vulnerable

```python
# settings/production.py
DEBUG = True

# or conditionally without explicit production check
DEBUG = os.getenv('ENVIRONMENT') == 'staging'
```

### Safe

```python
# settings/production.py
DEBUG = False

# or conditionally with explicit production check
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
```

Set `DEBUG = False` in production settings. Load the setting from an
environment variable with a safe default. Never hardcode `DEBUG = True`
in any production-bound settings file.

## Django SECRET_KEY

### Vulnerable

```python
# settings/production.py
SECRET_KEY = 'django-insecure-abc123def456'

# or a common default
SECRET_KEY = 'secret'

# or empty
SECRET_KEY = ''
```

### Safe

```python
# settings/production.py
from django.core.management.utils import get_random_secret_key

SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    SECRET_KEY = get_random_secret_key()

# or simpler: load from environment only
SECRET_KEY = os.getenv('SECRET_KEY')
```

Generate a unique `SECRET_KEY` with
`django.core.management.utils.get_random_secret_key()` and store it in
the `SECRET_KEY` environment variable. Load it at runtime without
fallbacks to hardcoded defaults.

## Django ALLOWED_HOSTS

### Vulnerable

```python
# settings/production.py
ALLOWED_HOSTS = ['*']
```

### Safe

```python
# settings/production.py
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'example.com').split(',')

# or explicitly
ALLOWED_HOSTS = ['example.com', 'www.example.com']
```

Set `ALLOWED_HOSTS` to an explicit list of hostnames. Load the list from
an environment variable in production. Never use `['*']` in production.

## Flask debug mode

### Vulnerable

```python
# app.py
app.debug = True
app.run(debug=True)

# or set in config
app.config['DEBUG'] = True
```

### Safe

```python
# app.py
app.debug = False

# or load from environment
app.config['DEBUG'] = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
```

Set `app.debug = False` in production. Load the debug flag from the
`FLASK_DEBUG` environment variable with a safe default. Never enable
`debug=True` in the `app.run()` call for production deployments.

## Flask secret_key

### Vulnerable

```python
# app.py
app.secret_key = 'dev'
app.secret_key = 'changeme'
app.secret_key = 'secret'
```

### Safe

```python
# app.py
app.secret_key = os.getenv('SECRET_KEY')

# or generated at startup
import secrets
app.secret_key = secrets.token_bytes(32)
```

Load `app.secret_key` from the `SECRET_KEY` environment variable. Never
hardcode short or common strings. For development, generate a random key
at startup if the variable is not set.

## FastAPI debug mode

### Vulnerable

```python
# main.py
app = FastAPI(debug=True)

# or in config
app = FastAPI(**{"debug": True})
```

### Safe

```python
# main.py
app = FastAPI(debug=False)

# or load from environment
debug_mode = os.getenv('DEBUG', 'False').lower() == 'true'
app = FastAPI(debug=debug_mode)
```

Set `debug=False` when constructing the FastAPI app. Load the debug flag
from an environment variable with a safe default. Never hardcode
`debug=True` in production code paths.

## Starlette debug mode

### Vulnerable

```python
# app.py
app = Starlette(debug=True)
```

### Safe

```python
# app.py
app = Starlette(debug=False)

# or load from environment
debug_mode = os.getenv('DEBUG', 'False').lower() == 'true'
app = Starlette(debug=debug_mode)
```

Set `debug=False` when constructing the Starlette app. Load the debug
flag from an environment variable with a safe default.
