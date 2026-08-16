# Python PII in logs patterns

Vulnerable and safe snippets for Python logging that the
`crypto.pii_in_logs` scanner recognizes.

## logging module

### Vulnerable

```python
import logging

logging.info(f"User {email} logged in: {password}")
logging.debug(f"Payment card: {credit_card}")
logging.warning(f"Token expired: {api_token}")
logging.exception(f"Auth failed for {password}")
```

### Safe

```python
logging.info("User %s logged in", user_id)
logging.debug("Payment processed: order_id=%s", order_id)
logging.warning("Token expired for user_id=%s", user_id)
```

Use `%s` formatting with identifiers, not f-strings with
sensitive values. Log user IDs, order IDs, and request IDs,
not credentials or PII.

## Full request logging

### Vulnerable

```python
logging.info("Request body: %s", request.data)
logging.debug("POST data: %s", str(request.POST))
```

### Safe

```python
logging.info(
    "Request: %s %s",
    request.method,
    request.path,
)
```

Never log full request bodies. They contain passwords, tokens,
and PII submitted by users.

## print in production

### Vulnerable

```python
print(f"DEBUG: token={token}, password={password}")
```

### Safe

```python
logger.debug("Auth attempt for user_id=%s", user_id)
```

Replace `print` with structured logging in production code.
`print` bypasses log level controls and redaction filters.
