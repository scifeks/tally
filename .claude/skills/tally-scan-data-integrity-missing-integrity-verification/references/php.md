# PHP data integrity verification patterns

Vulnerable-vs-safe snippets for the PHP HTTP, webhook, JWT, and include
patterns the `data_integrity.missing_integrity_verification` scanner
recognizes.

## file_get_contents: HTTP artifact download

### Vulnerable

```php
$url = "https://trusted-domain.com/plugin.php";
$plugin_code = file_get_contents($url);
eval($plugin_code);
```

### Safe

```php
$url = "https://trusted-domain.com/plugin.php";
$expected_hash = "abc123def456...";
$plugin_code = file_get_contents($url);
if (hash("sha256", $plugin_code) !== $expected_hash) {
    throw new Exception("Hash mismatch");
}
eval($plugin_code);
```

Compute the hash of the downloaded content using `hash("sha256", $content)`
and verify it matches the known-good value before evaluating or including.

## cURL: HTTP artifact download

### Vulnerable

```php
$ch = curl_init("https://trusted-domain.com/app.tar.gz");
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
$content = curl_exec($ch);
curl_close($ch);
file_put_contents("app.tar.gz", $content);
system("tar -xzf app.tar.gz");
```

### Safe

```php
$ch = curl_init("https://trusted-domain.com/app.tar.gz");
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
$content = curl_exec($ch);
curl_close($ch);
$expected_hash = "def789ghi012...";
if (hash("sha256", $content) !== $expected_hash) {
    throw new Exception("Hash mismatch");
}
file_put_contents("app.tar.gz", $content);
system("tar -xzf app.tar.gz");
```

Always verify the checksum of downloaded content before using it. Store
the known-good hash in a configuration file or environment variable.

## Webhook signature verification (generic HTTP)

### Vulnerable

```php
$payload = file_get_contents("php://input");
$data = json_decode($payload, true);
process_order($data);
http_response_code(200);
```

### Safe

```php
$payload = file_get_contents("php://input");
$secret = $_ENV["WEBHOOK_SECRET"];
$signature = $_SERVER["HTTP_X_HUB_SIGNATURE_256"] ?? "";

$expected = "sha256=" . hash_hmac("sha256", $payload, $secret);
if (!hash_equals($expected, $signature)) {
    http_response_code(401);
    die("Invalid signature");
}

$data = json_decode($payload, true);
process_order($data);
http_response_code(200);
```

Extract the signature from the request header (e.g.,
`X-Hub-Signature-256` for GitHub, `X-Signature` for custom webhooks).
Compute the HMAC using `hash_hmac("sha256", $payload, $secret)` and compare
with `hash_equals()` to prevent timing attacks.

## Firebase JWT: JWT signature verification

### Vulnerable

```php
use Firebase\JWT\JWT;

$token = str_replace("Bearer ", "", $_SERVER["HTTP_AUTHORIZATION"] ?? "");
$decoded = JWT::decode($token, new Key("", "none"));
$user_id = $decoded->user_id;
```

### Safe

```php
use Firebase\JWT\JWT;
use Firebase\JWT\Key;

$secret = $_ENV["JWT_SECRET"];
$token = str_replace("Bearer ", "", $_SERVER["HTTP_AUTHORIZATION"] ?? "");
try {
    $decoded = JWT::decode($token, new Key($secret, "HS256"));
    $user_id = $decoded->user_id;
} catch (Exception $e) {
    http_response_code(401);
    die("Invalid token");
}
```

Always pass a key and algorithm to `JWT::decode()`. Never use `"none"` as
the algorithm. Use a secret from an environment variable or secure
configuration, never hardcoded.

## Laravel Passport: JWT middleware

### Vulnerable

```php
Route::middleware("auth:api")->group(function () {
    Route::post("/orders", function (Request $request) {
        $user_id = $request->user()->id;
        process_order($user_id, $request->input("amount"));
    });
});
```

When using Laravel's default JWT authentication, verify the middleware is
configured to validate signatures. A misconfigured or custom middleware
might skip signature verification.

### Safe

```php
Route::middleware("auth:api")->group(function () {
    Route::post("/orders", function (Request $request) {
        $user_id = auth("api")->id();
        if (!$user_id) {
            abort(401, "Unauthenticated");
        }
        process_order($user_id, $request->input("amount"));
    });
});
```

Use Laravel's built-in authentication guards, which handle JWT verification
transparently. If using a custom guard, ensure the middleware calls
`verify_signature(true)` or equivalent.

## include/require: Remote code inclusion

### Vulnerable

```php
$plugin_url = $_GET["plugin"];
include $plugin_url;
```

### Safe

```php
$allowed_plugins = [
    "plugin_v1" => "https://trusted-domain.com/plugin_v1.php",
    "plugin_v2" => "https://trusted-domain.com/plugin_v2.php",
];
$plugin_name = $_GET["plugin"] ?? "plugin_v1";
if (!isset($allowed_plugins[$plugin_name])) {
    die("Unknown plugin");
}
$url = $allowed_plugins[$plugin_name];
$expected_hash = file_get_contents("/etc/plugin_hashes.json");
$hashes = json_decode($expected_hash, true);

$content = file_get_contents($url);
$actual_hash = hash("sha256", $content);
if ($hashes[$plugin_name] !== $actual_hash) {
    die("Hash mismatch");
}
eval("?>" . $content);
```

Maintain an allowlist of known-good plugins and their SHA256 hashes. Download
the plugin code, verify the hash, and use `eval()` only after validation. Never
directly `include()` a URL without verification.

## Symfony HttpClient: HTTP artifact download

### Vulnerable

```php
$client = HttpClient::create();
$response = $client->request("GET", "https://trusted-domain.com/data.json");
$data = json_decode($response->getContent(), true);
process_data($data);
```

### Safe

```php
$client = HttpClient::create();
$response = $client->request("GET", "https://trusted-domain.com/data.json");
$content = $response->getContent();
$expected_hash = "jkl345mno678...";
if (hash("sha256", $content) !== $expected_hash) {
    throw new Exception("Hash mismatch");
}
$data = json_decode($content, true);
process_data($data);
```

Always verify the hash or signature of downloaded content before using it,
even from trusted sources.
