# Python file permissions patterns

Vulnerable-vs-safe snippets for insecure file permission operations the
`misconfig.insecure_file_permissions` scanner recognizes. When multiple
safe forms exist, the canonical one is shown first.

## os.chmod with overly permissive mode

### Vulnerable

```python
import os

# Credential file
os.chmod('secrets.txt', 0o777)

# Config file
os.chmod('/etc/app/config.json', 0o666)

# Or using octal
os.chmod(key_file, 0777)
```

### Safe

```python
import os

# Credential file: owner read/write only
os.chmod('secrets.txt', 0o600)

# Config file: owner read/write, group read
os.chmod('/etc/app/config.json', 0o640)

# Explicitly restrictive
os.chmod(key_file, 0o600)
```

Never grant world-read or world-write permissions to credential, config, or
secret files. Use `0o600` for owner-only access or `0o640` for
owner-read/write and group-read access when shared with a specific group.

## os.umask to world access

### Vulnerable

```python
import os

# Remove all permission restrictions
os.umask(0)

# or explicitly
os.umask(0o000)

# Subsequent file operations lack restrictions
with open('config.txt', 'w') as f:
    f.write(sensitive_data)
```

### Safe

```python
import os

# Restrict to owner only: all others removed
os.umask(0o077)

# For specific files, set permissions explicitly
with open('config.txt', 'w') as f:
    f.write(sensitive_data)
os.chmod('config.txt', 0o600)

# Better: context manager pattern
old_umask = os.umask(0o077)
try:
    with open('config.txt', 'w') as f:
        f.write(sensitive_data)
finally:
    os.umask(old_umask)
```

Never call `os.umask(0)` or `os.umask(0o000)`. Use `os.umask(0o077)` to
restrict file creation to owner-only, or better, set permissions
explicitly on each sensitive file after creation.

## open() for secrets without mode restriction

### Vulnerable

```python
# Writing credential data without mode parameter
with open('db_password.txt', 'w') as f:
    f.write(password)

# or appending
with open('api_keys.txt', 'a') as f:
    f.write(token)
```

### Safe

```python
# Restrict to owner only (0o600 = rw-------)
with open('db_password.txt', 'w') as f:
    os.chmod('db_password.txt', 0o600)
    f.write(password)

# Better: set permissions before writing
os.open('db_password.txt', os.O_CREAT | os.O_WRONLY, mode=0o600)
with open('db_password.txt', 'w') as f:
    f.write(password)

# Or using pathlib with explicit mode
from pathlib import Path
Path('db_password.txt').write_text(password)
Path('db_password.txt').chmod(0o600)
```

Always specify a restrictive mode when creating files that will hold
credentials, API keys, or secrets. Use `mode=0o600` to restrict to
owner-only access.

## tempfile.mktemp() usage

### Vulnerable

```python
import tempfile

# mktemp() generates predictable names, vulnerable to symlink attacks
temp_path = tempfile.mktemp()
with open(temp_path, 'w') as f:
    f.write(sensitive_data)

# Race condition: file can be created by attacker between mktemp() and open()
```

### Safe

```python
import tempfile

# NamedTemporaryFile: cryptographically unique, owner-only by default
with tempfile.NamedTemporaryFile(delete=False, mode='w') as f:
    f.write(sensitive_data)
    temp_path = f.name

# Better: with explicit restrictive mode
with tempfile.NamedTemporaryFile(
    delete=False,
    mode='w',
    dir=tempfile.gettempdir()
) as f:
    os.chmod(f.name, 0o600)
    f.write(sensitive_data)
    temp_path = f.name

# Safest: use temp directory, clean up after
temp_dir = tempfile.mkdtemp(prefix='app_', mode=0o700)
try:
    temp_path = os.path.join(temp_dir, 'sensitive_data.txt')
    with open(temp_path, 'w') as f:
        f.write(sensitive_data)
finally:
    import shutil
    shutil.rmtree(temp_dir)
```

Replace `tempfile.mktemp()` with `tempfile.NamedTemporaryFile(delete=False)`
to create a cryptographically unique temp file with owner-only permissions
by default. Avoid race conditions between temp file name generation and
creation.

## tempfile.NamedTemporaryFile with delete=False

### Vulnerable

```python
import tempfile

# File persists on disk after process exit; permissions may be world-readable
temp = tempfile.NamedTemporaryFile(delete=False)
temp.write(b'secret_data')
temp.close()

# File is now world-readable depending on system umask
```

### Safe

```python
import tempfile
import os

# Set restrictive permissions explicitly
temp = tempfile.NamedTemporaryFile(delete=False, mode='w')
os.chmod(temp.name, 0o600)
temp.write('secret_data')
temp.close()

# Better: use context manager with cleanup
with tempfile.NamedTemporaryFile(delete=True, mode='w') as temp:
    temp.write('secret_data')
    # File is automatically deleted when context exits

# For persistent temp files: use mkdtemp + explicit chmod
temp_dir = tempfile.mkdtemp(mode=0o700)
try:
    temp_path = os.path.join(temp_dir, 'data.txt')
    with open(temp_path, 'w') as f:
        f.write('secret_data')
    os.chmod(temp_path, 0o600)
    # Use temp_path...
finally:
    import shutil
    shutil.rmtree(temp_dir)
```

When using `tempfile.NamedTemporaryFile(delete=False)`, explicitly set
owner-only permissions with `os.chmod(temp.name, 0o600)` before writing
sensitive data. Prefer `delete=True` when cleanup is feasible to avoid
leaving sensitive files on disk.
