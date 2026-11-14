# Python reflected XSS patterns

Vulnerable-vs-safe snippets for Python frameworks where
same-request data reaches an HTML rendering context. When multiple
safe forms exist, the canonical one is shown first.

## Flask f-string response

### Vulnerable

```python
@app.route("/search")
def search():
    query = request.args.get("q", "")
    return f"<h1>Results for: {query}</h1>"
```

### Safe

```python
@app.route("/search")
def search():
    query = request.args.get("q", "")
    return render_template("search.html", query=query)
```

Jinja2 auto-escapes template variables in Flask. Use
`render_template()` instead of building HTML strings. If a string
response is needed, call `markupsafe.escape(query)`.

## Flask render_template_string

### Vulnerable

```python
@app.route("/greet")
def greet():
    name = request.args.get("name", "")
    return render_template_string(
        "<p>Hello " + name + "</p>"
    )
```

### Safe

```python
@app.route("/greet")
def greet():
    name = request.args.get("name", "")
    return render_template_string(
        "<p>Hello {{ name }}</p>",
        name=name,
    )
```

Concatenating user input into the template string creates a
server-side template injection, not just XSS. Pass variables
through the template context.

## Django HttpResponse

### Vulnerable

```python
def search(request):
    q = request.GET.get("q", "")
    return HttpResponse(f"<p>Search: {q}</p>")
```

### Safe

```python
def search(request):
    q = request.GET.get("q", "")
    return render(request, "search.html", {"q": q})
```

Django templates auto-escape by default. Use `render()` with a
template. If `HttpResponse` is needed, call
`django.utils.html.escape(q)`.

## Django template with request context

### Vulnerable

```html
{% autoescape off %}
<p>You searched for: {{ request.GET.q }}</p>
{% endautoescape %}
```

### Safe

```html
<p>You searched for: {{ request.GET.q }}</p>
```

Remove `{% autoescape off %}`. Django auto-escapes by default.

## FastAPI HTMLResponse

### Vulnerable

```python
@app.get("/search")
async def search(q: str = ""):
    return HTMLResponse(f"<p>Results for: {q}</p>")
```

### Safe

```python
from markupsafe import escape

@app.get("/search")
async def search(q: str = ""):
    return HTMLResponse(f"<p>Results for: {escape(q)}</p>")
```

FastAPI does not auto-escape `HTMLResponse` content. Call
`markupsafe.escape()` on interpolated values, or use a Jinja2
template with auto-escaping enabled.
