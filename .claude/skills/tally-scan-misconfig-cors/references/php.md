# PHP CORS misconfiguration patterns

Vulnerable-vs-safe snippets for PHP web frameworks the `misconfig.cors`
scanner recognizes. When multiple safe forms exist, the canonical one is
shown first.

## Laravel CORS configuration

### Vulnerable

```php
<?php

return [
    'paths' => ['api/*'],
    'allowed_methods' => ['*'],
    'allowed_origins' => ['*'],
    'allowed_origins_patterns' => [],
    'allowed_headers' => ['*'],
    'exposed_headers' => [],
    'max_age' => 0,
    'supports_credentials' => true,
];
```

### Safe

```php
<?php

return [
    'paths' => ['api/*'],
    'allowed_methods' => ['GET', 'POST', 'PUT', 'DELETE'],
    'allowed_origins' => [
        'https://app.example.com',
        'https://trusted-partner.example.com',
    ],
    'allowed_origins_patterns' => [],
    'allowed_headers' => ['Content-Type', 'Authorization'],
    'exposed_headers' => [],
    'max_age' => 3600,
    'supports_credentials' => true,
];
```

Set `allowed_origins` to a specific list of trusted domains. Remove the
wildcard and do not use `*`. When credentials are enabled, enumerate origins
explicitly.

## Manual header reflection

### Vulnerable

```php
<?php

header('Access-Control-Allow-Origin: ' . $_SERVER['HTTP_ORIGIN']);
header('Access-Control-Allow-Credentials: true');
```

### Safe

```php
<?php

$allowedOrigins = [
    'https://app.example.com',
    'https://trusted-partner.example.com',
];

$origin = $_SERVER['HTTP_ORIGIN'] ?? '';

if (in_array($origin, $allowedOrigins, true)) {
    header('Access-Control-Allow-Origin: ' . $origin);
    header('Access-Control-Allow-Credentials: true');
}
```

Validate the Origin header against an allowlist before reflecting it. Only
set the Access-Control-Allow-Origin header if the origin is in the trusted
list.

## Manual wildcard with credentials

### Vulnerable

```php
<?php

header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Credentials: true');
```

### Safe

```php
<?php

$allowedOrigins = [
    'https://app.example.com',
];

$origin = $_SERVER['HTTP_ORIGIN'] ?? '';

if (in_array($origin, $allowedOrigins, true)) {
    header('Access-Control-Allow-Origin: ' . $origin);
    header('Access-Control-Allow-Credentials: true');
} else {
    http_response_code(403);
    die('Origin not allowed');
}
```

Never set `Access-Control-Allow-Origin: *` with credentials enabled. Browsers
will reject the combination, but the misconfiguration signals a control flow
bug. Enumerate origins explicitly.

## XML/JSON endpoints with permissive CORS

### Vulnerable

```php
<?php

header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, PUT, DELETE');

$xml = $_POST['xml_data'];
$dom = new DOMDocument();
$dom->loadXML($xml);
```

### Safe

```php
<?php

$allowedOrigins = ['https://app.example.com'];
$origin = $_SERVER['HTTP_ORIGIN'] ?? '';

if (in_array($origin, $allowedOrigins, true)) {
    header('Access-Control-Allow-Origin: ' . $origin);
    header('Access-Control-Allow-Methods: POST');

    $xml = $_POST['xml_data'];
    $dom = new DOMDocument();
    $dom->loadXML($xml);
}
```

Restrict CORS on endpoints that parse XML or JSON from user input. Validate
origins and limit HTTP methods to only those required for the endpoint's
intended use.
