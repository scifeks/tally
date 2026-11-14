# Python HTTP header injection patterns

Vulnerable-vs-safe snippets for the Python web frameworks the
`injection.header` scanner recognizes. When multiple safe forms exist,
the canonical one is shown first.

## Django

### Vulnerable

```python
from django.http import HttpResponse
user_url = request.GET.get("redirect_to")
response = HttpResponse()
response["Location"] = user_url
return response
```

```python
filename = request.GET.get("name")
response["Content-Disposition"] = f"attachment; filename={filename}"
return response
```

### Safe

```python
from django.shortcuts import redirect
from urllib.parse import urlparse
user_url = request.GET.get("redirect_to")
parsed = urlparse(user_url)
if parsed.scheme in ("http", "https") and parsed.netloc in ALLOWED_DOMAINS:
    return redirect(user_url)
else:
    return redirect("home")
```

```python
import re
filename = request.GET.get("name")
if not re.match(r"^[a-zA-Z0-9._-]+$", filename):
    filename = "download"
response["Content-Disposition"] = f'attachment; filename="{filename}"'
return response
```

Django's `redirect()` helper validates URLs internally. For custom headers,
strip newlines or validate the value against a known-safe pattern before
assignment.

## Flask

### Vulnerable

```python
from flask import request, Response
url = request.args.get("goto")
return redirect(url)
```

```python
filename = request.args.get("file")
response = Response(data)
response.headers["Content-Disposition"] = f"attachment; filename={filename}"
return response
```

### Safe

```python
from flask import request, redirect, url_for
from urllib.parse import urlparse
goto = request.args.get("goto")
parsed = urlparse(goto)
if parsed.scheme in ("http", "https") and parsed.netloc in ALLOWED_DOMAINS:
    return redirect(goto)
else:
    return redirect(url_for("index"))
```

```python
import os
filename = request.args.get("file", "download.bin")
filename = os.path.basename(filename)
filename = "".join(c for c in filename if c.isalnum() or c in "._-")
response = Response(data)
response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
return response
```

Flask's `redirect()` performs basic URL parsing but does not validate the
domain. Always validate user-supplied URLs against an allowlist. For
Content-Disposition, sanitize filenames to allow only safe characters.

## Generic WSGI (stdlib)

### Vulnerable

```python
from urllib.parse import parse_qs
query = parse_qs(environ["QUERY_STRING"])
user_url = query.get("url", [""])[0]
start_response("302 Found", [("Location", user_url)])
return [b""]
```

### Safe

```python
from urllib.parse import parse_qs, urlparse
query = parse_qs(environ["QUERY_STRING"])
user_url = query.get("url", [""])[0]
parsed = urlparse(user_url)
if parsed.scheme in ("http", "https") and parsed.netloc in ALLOWED_DOMAINS:
    start_response("302 Found", [("Location", user_url)])
else:
    start_response("302 Found", [("Location", "/")])
return [b""]
```

Validate URLs before passing to `start_response`. The WSGI server does not
automatically strip newlines from header values.

## Newline filtering pattern

If you must accept user input in a header, filter it:

```python
def safe_header_value(value):
    """Remove CR and LF from header value to prevent injection."""
    return value.replace("\r", "").replace("\n", "")

user_input = request.args.get("x_custom")
response["X-Custom"] = safe_header_value(user_input)
```

This is a fallback when validation is not possible. Prefer allowlist
validation or built-in framework helpers.
