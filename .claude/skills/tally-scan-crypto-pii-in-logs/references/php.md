# PHP PII in logs patterns

Vulnerable and safe snippets for PHP logging that the
`crypto.pii_in_logs` scanner recognizes.

## Log facade

### Vulnerable

```php
Log::info("Payment: " . $creditCard);
Log::debug("Auth: password=$password");
Log::info("User data: " . json_encode($user));
```

### Safe

```php
Log::info("Payment processed", [
    'order_id' => $orderId,
]);
Log::debug("Auth attempt", [
    'user_id' => $userId,
]);
```

Use structured context arrays with identifiers only. Never
concatenate sensitive values into the message.

## error_log

### Vulnerable

```php
error_log("Login: user=$email, pass=$password");
```

### Safe

```php
error_log("Login attempt: user_id=$userId");
```

## Full request logging

### Vulnerable

```php
Log::info(json_encode($request->all()));
Log::debug("Request: " . print_r($_POST, true));
```

### Safe

```php
Log::info("Request received", [
    'method' => $request->method(),
    'path' => $request->path(),
]);
```

`$request->all()` includes passwords and tokens. Log only the
route and a request identifier.
