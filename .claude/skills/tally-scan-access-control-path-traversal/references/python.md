# Python path traversal patterns

Vulnerable-vs-safe snippets for the Python file operations and
frameworks the `access_control.path_traversal` scanner recognizes.
When multiple safe forms exist, the canonical one is shown first.

## os.path (stdlib)

### Vulnerable

```python
filename = request.args.get("file")
with open(os.path.join("/uploads", filename)) as f:
    return f.read()

base = "/var/www/static"
filepath = base + "/" + request.args.get("path")
with open(filepath) as f:
    return f.read()
```

### Safe

```python
from pathlib import Path
filename = request.args.get("file")
base = Path("/uploads")
filepath = (base / filename).resolve()
if not filepath.is_relative_to(base.resolve()):
    abort(403)
with open(filepath) as f:
    return f.read()

# or use os.path with realpath
base_real = os.path.realpath("/uploads")
filename = request.args.get("file")
filepath = os.path.realpath(os.path.join(base_real, filename))
if not filepath.startswith(base_real + os.sep):
    abort(403)
with open(filepath) as f:
    return f.read()
```

Always resolve the full path and verify it stays within the base
directory. Check both `.resolve()` / `.is_relative_to()` (pathlib) or
`realpath()` + `startswith` (os.path).

## pathlib (stdlib)

### Vulnerable

```python
base = Path("/uploads")
user_file = request.args.get("file")
filepath = base / user_file
with open(filepath) as f:
    return f.read()
```

### Safe

```python
from pathlib import Path
base = Path("/uploads").resolve()
user_file = request.args.get("file")
filepath = (base / user_file).resolve()
if not filepath.is_relative_to(base):
    abort(403)
with open(filepath) as f:
    return f.read()
```

The `/` operator does not normalize paths. Always call `.resolve()` on
the result and use `.is_relative_to()` to confirm containment. For
Python < 3.9, use:

```python
try:
    filepath.relative_to(base)
except ValueError:
    abort(403)
```

## Flask

### Vulnerable

```python
@app.route("/download")
def download():
    filename = request.args.get("file")
    return send_file(os.path.join("uploads", filename))

@app.route("/static/<path:file>")
def static_file(file):
    return send_file(os.path.join("static", file))
```

### Safe

```python
from flask import send_from_directory

@app.route("/download")
def download():
    filename = request.args.get("file")
    return send_from_directory("uploads", filename)

@app.route("/static/<path:file>")
def static_file(file):
    return send_from_directory("static", file)
```

`send_from_directory` validates the filename and verifies it stays
within the directory. Never use `send_file` with `os.path.join` on
request data; use `send_from_directory` instead.

## shutil

### Vulnerable

```python
src = "/var/important/file.txt"
dest_dir = request.args.get("dest")
shutil.copy(src, os.path.join(dest_dir, "backup.txt"))

dest_filename = request.args.get("name")
shutil.copy(src, os.path.join("/backups", dest_filename))
```

### Safe

```python
import os
from pathlib import Path

src = "/var/important/file.txt"
dest_dir = Path("/backups").resolve()
dest_filename = Path(request.args.get("name")).name
dest_path = (dest_dir / dest_filename).resolve()
if not dest_path.is_relative_to(dest_dir):
    abort(403)
shutil.copy(src, dest_path)

# or sanitize the filename
dest_filename = os.path.basename(request.args.get("name"))
shutil.copy(src, os.path.join("/backups", dest_filename))
```

Use `.resolve()` and containment validation, or extract the
basename with `os.path.basename()` to strip directory components.

## Django

### Vulnerable

```python
user_file = request.GET.get("file")
with open(os.path.join("uploads", user_file)) as f:
    return FileResponse(f)
```

### Safe

```python
from pathlib import Path
from django.http import FileResponse

user_file = request.GET.get("file")
base = Path("uploads").resolve()
filepath = (base / user_file).resolve()
if not filepath.is_relative_to(base):
    return HttpResponseForbidden()
with open(filepath) as f:
    return FileResponse(f)
```

Resolve and validate containment before passing to any file operation.
