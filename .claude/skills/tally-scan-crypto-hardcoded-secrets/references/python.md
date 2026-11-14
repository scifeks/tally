# Python hardcoded secrets patterns

Vulnerable and safe snippets for Python secret management
that the `crypto.hardcoded_secrets` scanner recognizes.

## API keys and tokens

### Vulnerable

```python
API_KEY = "sk-proj-abc123def456"
STRIPE_SECRET = "sk_live_abc123"
token = "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

### Safe

```python
import os

API_KEY = os.environ["API_KEY"]
STRIPE_SECRET = os.environ["STRIPE_SECRET_KEY"]
token = os.environ["GITHUB_TOKEN"]
```

Load secrets from environment variables, a secrets manager,
or a `.env` file (gitignored) via `python-dotenv`.

## Django SECRET_KEY

### Vulnerable

```python
SECRET_KEY = "django-insecure-abc123xyz"
```

### Safe

```python
import os

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
```

## AWS credentials

### Vulnerable

```python
aws_access_key_id = "AKIAIOSFODNN7EXAMPLE"
aws_secret_access_key = "wJalrXUtnFEMI/K7MDENG/bPxRf"
```

### Safe

```python
import boto3

session = boto3.Session()
client = session.client('s3')
```

boto3 resolves credentials from the standard chain:
environment variables, `~/.aws/credentials`, IAM instance
profile. Never hardcode `AKIA` keys.

## Connection strings

### Vulnerable

```python
DATABASE_URL = (
    "postgresql://admin:hunter2@prod.db.example.com/app"
)
```

### Safe

```python
DATABASE_URL = os.environ["DATABASE_URL"]
```

## Private keys

### Vulnerable

```python
PRIVATE_KEY = """-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA...
-----END RSA PRIVATE KEY-----"""
```

### Safe

```python
with open(os.environ["KEY_FILE_PATH"]) as f:
    PRIVATE_KEY = f.read()
```

Store private keys in files outside the repo, referenced by
path through an environment variable.
