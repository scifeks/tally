# Python blind XSS patterns

Vulnerable-vs-safe snippets for Python frameworks where
user-submitted data is stored and later rendered in admin, email,
or internal contexts without escaping.

## Django admin template with |safe

### Vulnerable

```python
# admin view
def ticket_detail(request, ticket_id):
    ticket = Ticket.objects.get(id=ticket_id)
    return render(request, "admin/ticket.html", {
        "ticket": ticket,
    })
```

```html
<!-- admin/ticket.html -->
<div class="ticket-body">{{ ticket.body|safe }}</div>
<p>Submitted by: {{ ticket.submitter_name|safe }}</p>
```

### Safe

```html
<div class="ticket-body">{{ ticket.body }}</div>
<p>Submitted by: {{ ticket.submitter_name }}</p>
```

Admin templates need the same escaping as public-facing templates.
Remove `|safe`. If the field must render HTML, sanitize at write
time with `bleach.clean()`.

## Django email template

### Vulnerable

```python
def send_ticket_notification(ticket):
    html = render_to_string("email/ticket.html", {
        "ticket": ticket,
    })
    send_mail("New ticket", "", "noreply@example.com",
              [admin_email], html_message=html)
```

```html
<!-- email/ticket.html -->
{% autoescape off %}
<p>{{ ticket.body }}</p>
{% endautoescape %}
```

### Safe

```html
<p>{{ ticket.body }}</p>
```

Remove `{% autoescape off %}`. Django auto-escapes template
variables by default. HTML email clients render scripts in some
configurations.

## Flask log viewer with Markup()

### Vulnerable

```python
@app.route("/admin/logs")
def view_logs():
    entries = LogEntry.query.order_by(
        LogEntry.created_at.desc()
    ).limit(100).all()
    rendered = [
        Markup(f"<tr><td>{e.message}</td></tr>")
        for e in entries
    ]
    return render_template("admin/logs.html", rows=rendered)
```

### Safe

```python
@app.route("/admin/logs")
def view_logs():
    entries = LogEntry.query.order_by(
        LogEntry.created_at.desc()
    ).limit(100).all()
    return render_template("admin/logs.html", entries=entries)
```

```html
{% for entry in entries %}
<tr><td>{{ entry.message }}</td></tr>
{% endfor %}
```

Let Jinja2 auto-escape the values. Wrapping with `Markup()` in
Python bypasses the template engine's escaping. Log entries often
contain user-controlled data (usernames, search queries, request
paths).

## Report generation (WeasyPrint / xhtml2pdf)

### Vulnerable

```python
html = render_to_string("reports/findings.html", {
    "findings": findings,
})
pdf = HTML(string=html).write_pdf()
```

```html
<!-- reports/findings.html -->
{% for f in findings %}
<tr><td>{{ f.description|safe }}</td></tr>
{% endfor %}
```

### Safe

```html
{% for f in findings %}
<tr><td>{{ f.description }}</td></tr>
{% endfor %}
```

PDF generators render HTML internally. If the template disables
escaping on user-sourced fields, the PDF can contain malicious
content. Remove `|safe` and let auto-escaping work.
