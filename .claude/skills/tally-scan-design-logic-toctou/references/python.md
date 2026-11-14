# Python TOCTOU race condition patterns

Vulnerable-vs-safe snippets for the Python file and database operations
the `design_logic.toctou` scanner recognizes.

## os/pathlib file operations

### Vulnerable

```python
import os
if os.path.exists(user_file):
    content = open(user_file).read()

if os.path.isfile(target):
    with open(target, 'r') as f:
        data = f.read()

if os.access(config_path, os.W_OK):
    with open(config_path, 'w') as f:
        f.write(new_config)
```

### Safe

```python
import os
try:
    with open(user_file, 'r') as f:
        content = f.read()
except FileNotFoundError:
    content = None

from pathlib import Path
try:
    content = Path(target).read_text()
except FileNotFoundError:
    pass

try:
    with open(config_path, 'w') as f:
        f.write(new_config)
except PermissionError:
    log_error("Cannot write to config")
```

Eliminate the check-then-use pattern. Open directly and handle
FileNotFoundError or PermissionError at the point of use.

## tempfile (secure temporary file creation)

### Vulnerable

```python
import tempfile
import os

tmpdir = tempfile.gettempdir()
filepath = os.path.join(tmpdir, f"upload_{user_id}.tmp")
if not os.path.exists(filepath):
    with open(filepath, 'w') as f:
        f.write(user_data)
```

### Safe

```python
import tempfile

fd, filepath = tempfile.mkstemp(prefix="upload_", suffix=".tmp")
try:
    with os.fdopen(fd, 'w') as f:
        f.write(user_data)
finally:
    os.unlink(filepath)

with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
    f.write(user_data)
    temp_path = f.name
try:
    pass
finally:
    os.unlink(temp_path)
```

`tempfile.mkstemp()` creates and opens a file descriptor atomically with
mode 0600 (owner-readable only). No race window. The file is created in
the OS temp directory with secure permissions.

## os.makedirs with exist_ok

### Vulnerable

```python
import os

def create_user_dir(user_id):
    user_dir = f"/data/users/{user_id}"
    if not os.path.exists(user_dir):
        os.makedirs(user_dir)
    return user_dir
```

### Safe

```python
import os

def create_user_dir(user_id):
    user_dir = f"/data/users/{user_id}"
    os.makedirs(user_dir, exist_ok=True)
    return user_dir
```

`os.makedirs(path, exist_ok=True)` is atomic and safe. It creates the
directory structure and succeeds even if the directory already exists.

## Django ORM get_or_create

### Vulnerable

```python
from django.contrib.auth.models import User

email = request.POST.get('email')
if not User.objects.filter(email=email).exists():
    user = User.objects.create(email=email, username=email)
else:
    user = User.objects.get(email=email)
```

### Safe

```python
from django.contrib.auth.models import User

email = request.POST.get('email')
user, created = User.objects.get_or_create(
    email=email,
    defaults={'username': email}
)
```

`get_or_create()` is atomic at the database level. It uses INSERT ... ON
CONFLICT or equivalent, eliminating the race between the check and the
insert.

## SQLAlchemy with_for_update (pessimistic locking)

### Vulnerable

```python
from sqlalchemy import select

def transfer_balance(from_id, to_id, amount):
    from_user = session.query(User).filter_by(id=from_id).first()
    if from_user.balance >= amount:
        from_user.balance -= amount
        to_user = session.query(User).filter_by(id=to_id).first()
        to_user.balance += amount
        session.commit()
```

### Safe

```python
from sqlalchemy import select

def transfer_balance(from_id, to_id, amount):
    from_user = session.query(User).filter_by(
        id=from_id
    ).with_for_update().first()
    if from_user.balance >= amount:
        from_user.balance -= amount
        to_user = session.query(User).filter_by(
            id=to_id
        ).with_for_update().first()
        to_user.balance += amount
        session.commit()
    else:
        session.rollback()
        raise ValueError("Insufficient balance")
```

`with_for_update()` acquires a row-level lock on the selected rows,
preventing concurrent modifications. The lock is held until the
transaction commits.

## Database balance/quota atomicity

### Vulnerable

```python
user = User.objects.get(id=user_id)
if user.balance >= amount:
    user.balance -= amount
    user.save()
```

### Safe

```python
from django.db.models import F
from django.db import connection

cursor = connection.cursor()
cursor.execute(
    "UPDATE users SET balance = balance - %s WHERE id = %s AND balance >= %s",
    [amount, user_id, amount]
)
if cursor.rowcount == 0:
    raise ValueError("Insufficient balance")
```

Perform the check and the debit in a single atomic UPDATE statement. The
database checks the balance and updates it in one operation. If zero rows
were affected, the balance was insufficient.
