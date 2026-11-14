# Python stored XSS patterns

Vulnerable-vs-safe snippets for Python frameworks where
persistence-sourced data reaches an HTML rendering context. When
multiple safe forms exist, the canonical one is shown first.

## Django templates (|safe filter)

### Vulnerable

```python
# views.py
def profile(request, user_id):
    user = User.objects.get(id=user_id)
    return render(request, "profile.html", {"user": user})
```

```html
<!-- profile.html -->
<div class="bio">{{ user.bio|safe }}</div>
```

### Safe

```html
<div class="bio">{{ user.bio }}</div>
```

Django auto-escapes template variables by default. The `|safe`
filter disables escaping. Remove `|safe` to activate protection.
If the field must render trusted HTML, sanitize at write time with
`bleach.clean()` before storing.

## Django mark_safe()

### Vulnerable

```python
from django.utils.safestring import mark_safe

def render_comment(comment):
    return mark_safe(f"<p>{comment.body}</p>")
```

### Safe

```python
from django.utils.html import escape

def render_comment(comment):
    return f"<p>{escape(comment.body)}</p>"
```

`mark_safe()` tells Django the string is pre-escaped. If the
string contains user data from the database, it is not safe.
Use `escape()` or let the template engine handle escaping.

## Django autoescape off

### Vulnerable

```html
{% autoescape off %}
<div>{{ article.content }}</div>
{% endautoescape %}
```

### Safe

```html
<div>{{ article.content }}</div>
```

The `{% autoescape off %}` block disables escaping for all
variables inside it. Remove the block. If mixed content is needed,
use `|safe` only on trusted, pre-sanitized values.

## Flask / Jinja2 Markup()

### Vulnerable

```python
from markupsafe import Markup

@app.route("/post/<int:post_id>")
def show_post(post_id):
    post = db.session.get(Post, post_id)
    return render_template(
        "post.html",
        content=Markup(post.body),
    )
```

### Safe

```python
@app.route("/post/<int:post_id>")
def show_post(post_id):
    post = db.session.get(Post, post_id)
    return render_template("post.html", content=post.body)
```

Jinja2 auto-escapes by default in Flask. Wrapping a value with
`Markup()` bypasses escaping. Remove the wrapper and let the
template engine escape the value.

## Flask f-string response

### Vulnerable

```python
@app.route("/user/<int:user_id>")
def user_page(user_id):
    user = db.session.get(User, user_id)
    return f"<h1>{user.display_name}</h1><p>{user.bio}</p>"
```

### Safe

```python
from markupsafe import escape

@app.route("/user/<int:user_id>")
def user_page(user_id):
    user = db.session.get(User, user_id)
    return render_template("user.html", user=user)
```

f-string responses bypass the template engine entirely. Use
`render_template()` for HTML output. If a plain string response
is needed, call `escape()` on every interpolated value.

## FastAPI HTMLResponse

### Vulnerable

```python
from fastapi.responses import HTMLResponse

@app.get("/item/{item_id}")
async def show_item(item_id: int):
    item = await db.get_item(item_id)
    return HTMLResponse(
        f"<div>{item.description}</div>"
    )
```

### Safe

```python
from fastapi.responses import HTMLResponse
from markupsafe import escape

@app.get("/item/{item_id}")
async def show_item(item_id: int):
    item = await db.get_item(item_id)
    return HTMLResponse(
        f"<div>{escape(item.description)}</div>"
    )
```

FastAPI's `HTMLResponse` does not escape content. Call
`markupsafe.escape()` on interpolated values, or use a template
engine (Jinja2) with auto-escaping enabled.
