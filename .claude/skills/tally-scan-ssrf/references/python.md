# Python SSRF patterns

Safe and vulnerable code snippets for the Python HTTP libraries the
`ssrf` scanner recognizes. When multiple safe forms exist, the
canonical one is shown first.

## requests

### Vulnerable

```python
webhook_url = request.args.get("url")
response = requests.get(webhook_url)

user_callback = request.json["callback_url"]
requests.post(user_callback, json={"status": "done"})
```

### Safe

```python
from urllib.parse import urlparse

ALLOWED_DOMAINS = {"api.trusted.com", "webhook.service.io"}

webhook_url = request.args.get("url")
parsed = urlparse(webhook_url)
if parsed.hostname not in ALLOWED_DOMAINS:
    raise ValueError("URL not in allowlist")
response = requests.get(webhook_url)
```

To block private IP ranges:

```python
from urllib.parse import urlparse
import ipaddress

def is_private_ip(hostname):
    try:
        ip = ipaddress.ip_address(hostname)
        return ip.is_private or ip.is_loopback
    except ValueError:
        return False

webhook_url = request.args.get("url")
parsed = urlparse(webhook_url)
if is_private_ip(parsed.hostname):
    raise ValueError("Private IP ranges not allowed")
response = requests.get(webhook_url)
```

## urllib and urllib3

### Vulnerable

```python
import urllib.request

user_url = request.data.get("fetch_url")
response = urllib.request.urlopen(user_url)

import urllib3

user_url = request.query_params.get("callback")
http = urllib3.PoolManager()
resp = http.request("GET", user_url)
```

### Safe

```python
from urllib.parse import urlparse
import urllib.request
import ipaddress

ALLOWED_DOMAINS = {"example.com"}

def validate_url(url):
    parsed = urlparse(url)
    if parsed.hostname not in ALLOWED_DOMAINS:
        raise ValueError("Domain not allowlisted")
    try:
        ip = ipaddress.ip_address(parsed.hostname)
        if ip.is_private or ip.is_loopback:
            raise ValueError("Private IP not allowed")
    except ValueError:
        pass
    return url

user_url = request.data.get("fetch_url")
validate_url(user_url)
response = urllib.request.urlopen(user_url)
```

## httpx

### Vulnerable

```python
import httpx

webhook_url = request.json.get("webhook_url")
client = httpx.Client()
response = client.get(webhook_url)

async def fetch(user_url):
    async with httpx.AsyncClient() as client:
        return await client.get(user_url)
```

### Safe

```python
from urllib.parse import urlparse
import httpx

ALLOWED_DOMAINS = {"api.example.com"}

def validate_url(url):
    parsed = urlparse(url)
    if parsed.hostname not in ALLOWED_DOMAINS:
        raise ValueError("Domain not allowlisted")
    return url

webhook_url = request.json.get("webhook_url")
validate_url(webhook_url)
client = httpx.Client()
response = client.get(webhook_url)
```

## aiohttp

### Vulnerable

```python
import aiohttp

async def fetch_webhook(user_url):
    async with aiohttp.ClientSession() as session:
        async with session.get(user_url) as resp:
            return await resp.json()
```

### Safe

```python
from urllib.parse import urlparse
import aiohttp

ALLOWED_DOMAINS = {"webhook.service.io"}

async def fetch_webhook(user_url):
    parsed = urlparse(user_url)
    if parsed.hostname not in ALLOWED_DOMAINS:
        raise ValueError("Domain not allowlisted")
    async with aiohttp.ClientSession() as session:
        async with session.get(user_url) as resp:
            return await resp.json()
```

## Dynamic URL construction (safe only with fixed domain)

When constructing URLs dynamically, keep the domain hardcoded:

```python
import requests

user_path = request.args.get("path")
safe_url = f"https://api.trusted.com/endpoint/{user_path}"
response = requests.get(safe_url)
```

The hardcoded domain ensures the request cannot reach arbitrary
hosts.
