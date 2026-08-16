# Python weak PRNG patterns

Vulnerable and safe snippets for Python PRNG usage the
`crypto.weak_prng` scanner recognizes.

## random module

### Vulnerable

```python
import random

token = ''.join(
    random.choice('abcdef0123456789')
    for _ in range(32)
)
session_id = random.getrandbits(128)
otp = random.randint(100000, 999999)
```

### Safe

```python
import secrets

token = secrets.token_hex(32)
session_id = secrets.token_urlsafe(32)
otp = secrets.randbelow(900000) + 100000
```

The `random` module uses Mersenne Twister, which is deterministic and
predictable after observing 624 outputs. The `secrets` module uses the
OS CSPRNG.

## uuid

### Vulnerable

```python
import uuid

token = str(uuid.uuid1())
```

### Safe

```python
token = str(uuid.uuid4())
```

`uuid1` encodes the timestamp and MAC address. `uuid4` generates a
random UUID from the OS CSPRNG.

## os.urandom (safe reference)

```python
import os

raw_bytes = os.urandom(32)
```

`os.urandom` reads from the OS CSPRNG. The `secrets` module wraps it
with a friendlier API.
