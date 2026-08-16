# Python race condition patterns

Vulnerable-vs-safe snippets for the Python concurrent operations the
`design_logic.race_condition` scanner recognizes.

## asyncio shared state mutation without lock

### Vulnerable

```python
import asyncio

counter = 0

async def increment():
    global counter
    current = counter
    await asyncio.sleep(0)
    counter = current + 1

async def main():
    await asyncio.gather(increment(), increment(), increment())
    print(counter)
```

### Safe

```python
import asyncio

counter = 0
counter_lock = asyncio.Lock()

async def increment():
    global counter
    async with counter_lock:
        current = counter
        await asyncio.sleep(0)
        counter = current + 1

async def main():
    await asyncio.gather(increment(), increment(), increment())
    print(counter)
```

Use `asyncio.Lock()` to protect access to shared state. Acquire the lock
with `async with lock:` around all read-modify-write sequences.

## Thread-unsafe global state in request handlers

### Vulnerable

```python
from flask import Flask, request

app = Flask(__name__)
user_data = {}

@app.route('/profile', methods=['POST'])
def update_profile():
    user_id = request.json['user_id']
    user_data[user_id] = request.json['profile']
    return {'status': 'ok'}

@app.route('/profile/<user_id>')
def get_profile(user_id):
    return user_data.get(user_id, {})
```

### Safe

```python
from flask import Flask, request, g
from threading import Lock

app = Flask(__name__)
lock = Lock()

@app.route('/profile', methods=['POST'])
def update_profile():
    user_id = request.json['user_id']
    with lock:
        g.user_data = request.json['profile']
    return {'status': 'ok'}

@app.route('/profile/<user_id>')
def get_profile(user_id):
    with lock:
        profile = g.get('user_data', {})
    return profile
```

Use Flask's `g` object to store request-scoped data, or guard global state
with `threading.Lock()`. For long-lived mutable state, prefer a database or
cache backend.

## Concurrent database read-modify-write

### Vulnerable

```python
def transfer_credits(user_id, amount):
    user = User.objects.get(id=user_id)
    if user.credits >= amount:
        user.credits -= amount
        user.save()
        return True
    return False
```

### Safe (Option 1: SELECT FOR UPDATE)

```python
from django.db import transaction

def transfer_credits(user_id, amount):
    with transaction.atomic():
        user = User.objects.select_for_update().get(id=user_id)
        if user.credits >= amount:
            user.credits -= amount
            user.save()
            return True
        return False
```

### Safe (Option 2: Atomic UPDATE)

```python
from django.db import connection

def transfer_credits(user_id, amount):
    cursor = connection.cursor()
    cursor.execute(
        "UPDATE users SET credits = credits - %s WHERE id = %s AND credits >= %s",
        [amount, user_id, amount]
    )
    return cursor.rowcount > 0
```

Use SELECT ... FOR UPDATE to lock the row during the read-modify-write, or
perform the check and update in a single atomic UPDATE statement.

## File operations without file locking

### Vulnerable

```python
import os

def increment_counter(counter_file):
    with open(counter_file, 'r') as f:
        count = int(f.read())
    count += 1
    with open(counter_file, 'w') as f:
        f.write(str(count))
```

### Safe

```python
import fcntl

def increment_counter(counter_file):
    with open(counter_file, 'r+') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            count = int(f.read())
            count += 1
            f.seek(0)
            f.truncate()
            f.write(str(count))
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
```

Use `fcntl.flock()` with LOCK_EX to acquire an exclusive lock before reading
and writing to the file. Hold the lock until the read-modify-write sequence
completes.

## asyncio shared dictionary across coroutines

### Vulnerable

```python
import asyncio

shared_cache = {}

async def update_cache(key, value):
    await asyncio.sleep(0.1)
    shared_cache[key] = value

async def fetch_cache(key):
    if key in shared_cache:
        value = shared_cache[key]
        await asyncio.sleep(0.1)
        return value
    return None

async def main():
    await asyncio.gather(
        update_cache('a', 1),
        fetch_cache('a'),
        update_cache('a', 2)
    )
```

### Safe

```python
import asyncio

shared_cache = {}
cache_lock = asyncio.Lock()

async def update_cache(key, value):
    await asyncio.sleep(0.1)
    async with cache_lock:
        shared_cache[key] = value

async def fetch_cache(key):
    async with cache_lock:
        if key in shared_cache:
            value = shared_cache[key]
    await asyncio.sleep(0.1)
    return value

async def main():
    await asyncio.gather(
        update_cache('a', 1),
        fetch_cache('a'),
        update_cache('a', 2)
    )
```

Protect all access to the shared cache with `asyncio.Lock()`. Acquire the
lock for the entire read or write operation.
