# PHP HTTP header injection patterns

Vulnerable-vs-safe snippets for the PHP web frameworks and stdlib the
`injection.header` scanner recognizes. When multiple safe forms exist,
the canonical one is shown first.

## header() with user input

### Vulnerable

```php
$redirect_url = $_GET["goto"];
header("Location: " . $redirect_url);
exit;
```

```php
$filename = $_GET["file"];
header("Content-Disposition: attachment; filename=" . $filename);
```

### Safe

```php
$redirect_url = $_GET["goto"];
$parsed = parse_url($redirect_url);
if (
    isset($parsed["scheme"], $parsed["host"]) &&
    in_array($parsed["scheme"], ["http", "https"]) &&
    in_array($parsed["host"], ALLOWED_DOMAINS)
) {
    header("Location: " . $redirect_url);
} else {
    header("Location: /");
}
exit;
```

```php
$filename = $_GET["file"];
$filename = basename($filename);
$filename = preg_replace("/[^a-zA-Z0-9._-]/", "", $filename);
if (empty($filename)) {
    $filename = "download.bin";
}
header("Content-Disposition: attachment; filename=\"" . $filename . "\"");
```

Always validate URLs with `parse_url()` and check both scheme and host.
For filenames, use `basename()` to strip directory traversal, then
whitelist safe characters.

## setcookie() with user data

### Vulnerable

```php
$user_pref = $_GET["preference"];
setcookie("pref", $user_pref);
```

```php
$session_id = $_POST["sid"];
setcookie("SESSIONID", $session_id);
```

### Safe

```php
$user_pref = $_GET["preference"];
$user_pref = preg_replace("/[^a-zA-Z0-9]/", "", $user_pref);
if (in_array($user_pref, ["light", "dark"])) {
    setcookie("pref", $user_pref, time() + 86400);
}
```

```php
$session_id = bin2hex(random_bytes(32));
setcookie("SESSIONID", $session_id, time() + 3600, "/", "", true, true);
```

Never use user input for cookie names or values. Generate session IDs
server-side. If user input must be a cookie value, validate it against an
allowlist.

## Refresh header

### Vulnerable

```php
$url = $_GET["redirect"];
header("Refresh: 5; url=" . $url);
```

### Safe

```php
$url = $_GET["redirect"];
$parsed = parse_url($url);
if (
    isset($parsed["scheme"], $parsed["host"]) &&
    in_array($parsed["scheme"], ["http", "https"]) &&
    in_array($parsed["host"], ALLOWED_DOMAINS)
) {
    header("Refresh: 5; url=" . $url);
} else {
    header("Refresh: 5; url=/");
}
```

Validate user-supplied URLs the same way as Location headers.

## WordPress $wp_safe_remote_*

### Vulnerable

```php
$user_url = $_GET["webhook"];
wp_remote_post($user_url, array("body" => $data));
header("X-Webhook-Status: " . $user_url);
```

### Safe

```php
$user_url = $_GET["webhook"];
$parsed = parse_url($user_url);
if (wp_http_validate_url($user_url)) {
    wp_remote_post($user_url, array("body" => $data));
    $status = "sent";
} else {
    $status = "invalid";
}
header("X-Webhook-Status: " . $status);
```

Use WordPress validation helpers (`wp_http_validate_url`,
`wp_kses_uri`) for URLs. Never place user input directly in headers; use
validated status strings instead.

## Generic header-value filtering pattern

If you must accept user input in a header, filter it:

```php
function safe_header_value($value) {
    return str_replace(array("\r", "\n"), "", $value);
}

$custom = $_GET["x_custom"];
header("X-Custom: " . safe_header_value($custom));
```

This is a fallback when validation is not possible. Prefer allowlist
validation or built-in framework helpers.
