# Python data integrity verification patterns

Vulnerable-vs-safe snippets for the Python HTTP, webhook, JWT, and
subprocess patterns the `data_integrity.missing_integrity_verification`
scanner recognizes.

## requests: HTTP artifact download

### Vulnerable

```python
import requests

url = "https://trusted-domain.com/app.tar.gz"
response = requests.get(url)
with open("app.tar.gz", "wb") as f:
    f.write(response.content)
subprocess.run(["tar", "-xzf", "app.tar.gz"])
```

### Safe

```python
import requests
import hashlib

url = "https://trusted-domain.com/app.tar.gz"
expected_hash = "abc123def456..."
response = requests.get(url)
actual_hash = hashlib.sha256(response.content).hexdigest()
if actual_hash != expected_hash:
    raise ValueError(f"Hash mismatch: {actual_hash}")
with open("app.tar.gz", "wb") as f:
    f.write(response.content)
subprocess.run(["tar", "-xzf", "app.tar.gz"])
```

Always download from trusted sources and verify the checksum before using
the artifact. Store the known-good hash in a config file, environment
variable, or code constant.

## urllib: HTTP artifact download

### Vulnerable

```python
import urllib.request

url = "https://trusted-domain.com/plugin.py"
urllib.request.urlretrieve(url, "plugin.py")
spec = importlib.util.spec_from_file_location("plugin", "plugin.py")
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)
```

### Safe

```python
import urllib.request
import hashlib

url = "https://trusted-domain.com/plugin.py"
expected_hash = "def789ghi012..."
urllib.request.urlretrieve(url, "plugin.py")
with open("plugin.py", "rb") as f:
    actual_hash = hashlib.sha256(f.read()).hexdigest()
if actual_hash != expected_hash:
    raise ValueError(f"Hash mismatch: {actual_hash}")
spec = importlib.util.spec_from_file_location("plugin", "plugin.py")
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)
```

Compute the hash of the downloaded file and compare it against the
known-good value before importing the module.

## Webhook signature verification (Flask)

### Vulnerable

```python
from flask import request

@app.route("/webhook", methods=["POST"])
def handle_webhook():
    data = request.get_json()
    process_order(data)
    return {"status": "ok"}
```

### Safe

```python
from flask import request
import hmac
import hashlib

WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]

@app.route("/webhook", methods=["POST"])
def handle_webhook():
    signature = request.headers.get("X-Hub-Signature-256")
    if not signature:
        return {"error": "Missing signature"}, 401
    expected = hmac.new(
        WEBHOOK_SECRET.encode(),
        request.data,
        hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return {"error": "Invalid signature"}, 401
    data = request.get_json()
    process_order(data)
    return {"status": "ok"}
```

Always validate the HMAC signature using `hmac.compare_digest()` to prevent
timing attacks. Extract the signature from the request header (GitHub uses
`X-Hub-Signature-256`, Stripe uses `Stripe-Signature`, etc.) and verify it
matches the computed HMAC of the raw request body.

## PyJWT: JWT signature verification

### Vulnerable

```python
import jwt

token = request.headers.get("Authorization", "").replace("Bearer ", "")
payload = jwt.decode(token, options={"verify_signature": False})
user_id = payload["user_id"]
```

### Safe

```python
import jwt
import os

SECRET = os.environ["JWT_SECRET"]
token = request.headers.get("Authorization", "").replace("Bearer ", "")
try:
    payload = jwt.decode(
        token,
        SECRET,
        algorithms=["HS256"]
    )
    user_id = payload["user_id"]
except jwt.InvalidSignatureError:
    return {"error": "Invalid token"}, 401
```

Always pass `verify_signature=True` (the default) and specify an explicit
`algorithms` list. Never include `"none"` in the algorithms. Use a secret
from an environment variable or secure configuration, never hardcoded.

## subprocess: Executing downloaded script

### Vulnerable

```python
import requests
import subprocess

url = "https://trusted-domain.com/setup.sh"
response = requests.get(url)
with open("setup.sh", "wb") as f:
    f.write(response.content)
subprocess.run(["bash", "setup.sh"], check=True)
```

### Safe

```python
import requests
import subprocess
import hashlib

url = "https://trusted-domain.com/setup.sh"
expected_hash = "jkl345mno678..."
response = requests.get(url)
actual_hash = hashlib.sha256(response.content).hexdigest()
if actual_hash != expected_hash:
    raise ValueError(f"Hash mismatch: {actual_hash}")
with open("setup.sh", "wb") as f:
    f.write(response.content)
subprocess.run(["bash", "setup.sh"], check=True)
```

Verify the downloaded script's hash before executing it. Never run
arbitrary scripts from the internet without verification.

## Dynamic module import with hash pinning

### Vulnerable

```python
import importlib.util

plugin_url = request.args.get("plugin_url")
urllib.request.urlretrieve(plugin_url, "dynamic_plugin.py")
spec = importlib.util.spec_from_file_location(
    "dynamic_plugin",
    "dynamic_plugin.py"
)
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)
```

### Safe

```python
import importlib.util
import hashlib

ALLOWED_HASHES = {
    "plugin_v1": "abc123...",
    "plugin_v2": "def456...",
}

plugin_name = request.args.get("plugin_name")
if plugin_name not in ALLOWED_HASHES:
    return {"error": "Unknown plugin"}, 400
expected_hash = ALLOWED_HASHES[plugin_name]

url = f"https://trusted-domain.com/plugins/{plugin_name}.py"
urllib.request.urlretrieve(url, "dynamic_plugin.py")
with open("dynamic_plugin.py", "rb") as f:
    actual_hash = hashlib.sha256(f.read()).hexdigest()
if actual_hash != expected_hash:
    raise ValueError(f"Hash mismatch: {actual_hash}")

spec = importlib.util.spec_from_file_location(
    "dynamic_plugin",
    "dynamic_plugin.py"
)
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)
```

Maintain an allowlist of known-good plugin names and their SHA256 hashes.
Verify the downloaded plugin matches the expected hash before importing.
