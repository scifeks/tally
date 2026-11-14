# Python template injection patterns

Vulnerable-vs-safe snippets for the Python template engines the
`injection.template` scanner recognizes. When multiple safe forms exist,
the canonical one is shown first.

## Jinja2 (Flask)

### Vulnerable

```python
from flask import Flask, render_template_string

@app.route('/hello')
def hello(name):
    template = f"Hello {name}!"
    return render_template_string(template)

@app.route('/test')
def test(user_input):
    return render_template_string(user_input)
```

### Safe

```python
from flask import Flask, render_template

@app.route('/hello')
def hello(name):
    return render_template('template.html', name=name)

@app.route('/test')
def test(user_input):
    # Pass data through context, not template source
    return render_template_string(
        'Hello {{ name }}!',
        name=user_input
    )
```

`render_template_string()` is safe when the template source is a
literal string and user data goes through the context dict. Never
interpolate user input into the template string itself.

## Jinja2 (direct)

### Vulnerable

```python
from jinja2 import Template, Environment

# Direct template instantiation
template = Template(user_input)
result = template.render()

# Environment with dynamic template
env = Environment()
template = env.from_string(user_input)
result = template.render()
```

### Safe

```python
from jinja2 import Environment

env = Environment()
template = env.from_string('Hello {{ name }}!')
result = template.render(name=user_input)

# Or load from a file
from jinja2 import FileSystemLoader, Environment
env = Environment(loader=FileSystemLoader('templates'))
template = env.get_template('template.html')
result = template.render(name=user_input)
```

User input goes through the render context, never into the template
source. Load static templates from files, not from request data.

## Mako

### Vulnerable

```python
from mako.template import Template, TemplateLookup

# Direct instantiation
template = Template(user_input)
result = template.render()

# Dynamic lookup
lookup = TemplateLookup(directories=['templates'])
template = lookup.get_template(user_input)
result = template.render()
```

### Safe

```python
from mako.template import TemplateLookup

# File-based templates only
lookup = TemplateLookup(directories=['templates'])
template = lookup.get_template('mytemplate.html')
result = template.render(name=user_input)

# Or use SandboxedLookup for restricted execution
from mako.lookup import TemplateLookup
from mako import parsetree
lookup = TemplateLookup(
    directories=['templates'],
    module_filename='./mako_modules'
)
template = lookup.get_template('mytemplate.html')
result = template.render_unicode(name=user_input)
```

Load templates from the filesystem only. Template filenames should be
hardcoded or validated against an allowlist. If dynamic template
source is unavoidable, use `SandboxedLookup`.

## Django templates

### Vulnerable

```python
from django.template import Template, Context

# Direct template instantiation
template = Template(user_input)
context = Context({'name': user_name})
result = template.render(context)
```

### Safe

```python
from django.template.loader import render_to_string
from django.shortcuts import render

# Use render() in views
return render(request, 'template.html', {'name': user_name})

# Or use render_to_string()
result = render_to_string('template.html', {'name': user_name})
```

Django's template system is safe by default when templates are loaded
from files. Never instantiate `Template` directly with request data.

## string.Template

### Vulnerable

```python
import string

# User input becomes the template source
template = string.Template(user_input)
result = template.substitute(data=data)

# Derived substitution
template_str = f"Value: {user_input}"
template = string.Template(template_str)
result = template.substitute()
```

### Safe

```python
import string

# Template is a literal string
template = string.Template('Value: $data')
result = template.substitute(data=user_input)

# Or use .safe_substitute() for missing keys
template = string.Template('Hello $name!')
result = template.safe_substitute(name=user_input)
```

`string.Template` is simpler than Jinja2 and less powerful, but still
supports code execution if the template source is user-controlled.
Keep the template literal and pass data through substitution.
