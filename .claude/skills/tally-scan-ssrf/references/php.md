# PHP SSRF patterns

Safe and vulnerable code snippets for the PHP HTTP libraries the
`ssrf` scanner recognizes. When multiple safe forms exist, the
canonical one is shown first.

## file_get_contents with URL wrappers

### Vulnerable

```php
$url = $_POST["url"];
$content = file_get_contents($url);

$user_image_url = $_GET["image"];
$data = file_get_contents($user_image_url);
```

### Safe

```php
$allowed_domains = ["cdn.example.com", "images.trusted.io"];

$url = $_POST["url"];
$parsed = parse_url($url);
if (!in_array($parsed["host"], $allowed_domains)) {
    throw new Exception("Domain not allowlisted");
}

$ip = gethostbyname($parsed["host"]);
if (filter_var($ip, FILTER_VALIDATE_IP,
    FILTER_FLAG_NO_PRIV_RANGE) === false) {
    throw new Exception("Private IP not allowed");
}

$content = file_get_contents($url);
```

Alternatively, disable URL wrappers in `php.ini`:

```
allow_url_fopen = Off
allow_url_include = Off
```

## curl functions

### Vulnerable

```php
$ch = curl_init();
curl_setopt($ch, CURLOPT_URL, $_POST["webhook_url"]);
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
$response = curl_exec($ch);
```

### Safe

```php
$allowed_domains = ["api.example.com", "webhook.service.io"];

$user_url = $_POST["webhook_url"];
$parsed = parse_url($user_url);

if (!in_array($parsed["host"], $allowed_domains)) {
    throw new Exception("Domain not allowlisted");
}

$ip = gethostbyname($parsed["host"]);
if (!filter_var($ip, FILTER_VALIDATE_IP,
    FILTER_FLAG_NO_PRIV_RANGE)) {
    throw new Exception("Private IP not allowed");
}

$ch = curl_init();
curl_setopt($ch, CURLOPT_URL, $user_url);
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
$response = curl_exec($ch);
curl_close($ch);
```

## Laravel HTTP client

### Vulnerable

```php
$url = request()->input("webhook_url");
$response = Http::get($url);

$callback = request()->json("callback");
Http::post($callback, ["status" => "done"]);
```

### Safe

```php
$allowed = ["api.example.com", "webhook.service.io"];

$url = request()->input("webhook_url");
$parsed = parse_url($url);
if (!in_array($parsed["host"], $allowed)) {
    abort(400, "Domain not allowlisted");
}

$response = Http::get($url);
```

## Guzzle

### Vulnerable

```php
use GuzzleHttp\Client;

$client = new Client();
$user_url = request()->input("callback_url");
$response = $client->request("GET", $user_url);
```

### Safe

```php
use GuzzleHttp\Client;

$allowed_domains = ["api.trusted.com"];

$client = new Client();
$user_url = request()->input("callback_url");
$parsed = parse_url($user_url);

if (!in_array($parsed["host"], $allowed_domains)) {
    throw new Exception("Domain not allowlisted");
}

$response = $client->request("GET", $user_url);
```

## fopen with URL

### Vulnerable

```php
$user_url = $_GET["source"];
$handle = fopen($user_url, "r");
$content = stream_get_contents($handle);
fclose($handle);
```

### Safe

```php
$allowed = ["ftp.example.com"];

$user_url = $_GET["source"];
$parsed = parse_url($user_url);

if ($parsed["scheme"] === "file") {
    throw new Exception("file:// scheme not allowed");
}

if (!in_array($parsed["host"], $allowed)) {
    throw new Exception("Host not allowlisted");
}

$handle = fopen($user_url, "r");
$content = stream_get_contents($handle);
fclose($handle);
```

Better: disable URL wrappers and use curl or dedicated FTP
libraries instead.

## Dynamic URL construction (safe only with fixed domain)

When constructing URLs dynamically, keep the domain hardcoded:

```php
$user_path = request()->input("path");
$safe_url = "https://api.trusted.com/endpoint/" . urlencode(
    $user_path
);
$response = Http::get($safe_url);
```

The hardcoded domain ensures the request cannot reach arbitrary
hosts.
