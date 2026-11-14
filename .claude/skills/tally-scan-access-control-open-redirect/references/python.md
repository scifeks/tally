# Python open redirect patterns

Vulnerable-vs-safe snippets for the Python web frameworks the
`access_control.open_redirect` scanner recognizes. When multiple safe
forms exist, the canonical one is shown first.

## Django

### Vulnerable

```python
def login_redirect(request):
    next_url = request.GET.get('next', '/dashboard')
    return redirect(next_url)

def go_to_url(request):
    url = request.POST['redirect_to']
    return HttpResponseRedirect(url)
```

### Safe

```python
from django.utils.http import url_has_allowed_host_and_scheme

def login_redirect(request):
    next_url = request.GET.get('next', '/dashboard')
    if url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={'example.com'}
    ):
        return redirect(next_url)
    return redirect('/dashboard')

def go_to_url(request):
    url = request.POST['redirect_to']
    allowed = {'https://example.com', 'https://app.example.com'}
    if url in allowed:
        return HttpResponseRedirect(url)
    return HttpResponseRedirect('/dashboard')
```

Django's `url_has_allowed_host_and_scheme` validates both the host
and the scheme. Always check its return value before redirecting.
For a fixed allowlist, compare the parsed URL host against your
permitted domains.

## Flask

### Vulnerable

```python
@app.route('/login', methods=['POST'])
def login():
    next_url = request.args.get('next')
    return redirect(next_url)
```

### Safe

```python
from urllib.parse import urlparse
from werkzeug.security import url_has_allowed_host_and_schemes

@app.route('/login', methods=['POST'])
def login():
    next_url = request.args.get('next', url_for('dashboard'))
    if url_has_allowed_host_and_schemes(
        next_url,
        allowed_hosts=['example.com']
    ):
        return redirect(next_url)
    return redirect(url_for('dashboard'))
```

Werkzeug's `url_has_allowed_host_and_schemes` function validates
the URL. Alternatively, use Flask's `url_for()` to generate internal
redirect targets.

## FastAPI

### Vulnerable

```python
from fastapi import FastAPI
from fastapi.responses import RedirectResponse

@app.get('/login')
def login(next: str = None):
    if next:
        return RedirectResponse(url=next)
    return RedirectResponse(url='/dashboard')
```

### Safe

```python
from urllib.parse import urlparse
from fastapi import FastAPI
from fastapi.responses import RedirectResponse

ALLOWED_HOSTS = {'example.com', 'app.example.com'}

def is_safe_redirect(url: str) -> bool:
    if url.startswith('/'):
        return True
    try:
        parsed = urlparse(url)
        return parsed.netloc in ALLOWED_HOSTS
    except Exception:
        return False

@app.get('/login')
def login(next: str = None):
    if next and is_safe_redirect(next):
        return RedirectResponse(url=next)
    return RedirectResponse(url='/dashboard')
```

Always validate the redirect target. For same-origin redirects, use
relative paths (starting with `/`). For cross-domain redirects,
maintain an explicit allowlist.

## Relative-path-only redirect (safe)

```python
def go_to_page(request):
    page = request.GET.get('page', 'home')
    if page not in {'home', 'about', 'contact'}:
        page = 'home'
    return redirect(f'/{page}')
```

Relative paths that do not include a domain or protocol are
inherently same-origin and safe.

## Anti-pattern: ignoring the validation result

```python
from django.utils.http import url_has_allowed_host_and_scheme

def bad_validation(request):
    url = request.GET.get('next')
    url_has_allowed_host_and_scheme(
        url,
        allowed_hosts={'example.com'}
    )
    return redirect(url)
```

The function is called but the return value is not used. The
redirect is still unsafe. Always assign or check the result.
