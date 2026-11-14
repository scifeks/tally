# PHP hardcoded secrets patterns

Vulnerable and safe snippets for PHP secret management that
the `crypto.hardcoded_secrets` scanner recognizes.

## Variables and constants

### Vulnerable

```php
$apiKey = "sk_live_abc123def456";
define('DB_PASSWORD', 'hunter2');
const STRIPE_KEY = 'sk_live_xxxx';
```

### Safe

```php
$apiKey = getenv('API_KEY');
$dbPassword = $_ENV['DB_PASSWORD'];
```

## Laravel config

### Vulnerable

```php
'key' => 'base64:hardcoded_key_value_here',
'password' => 'admin123',
```

### Safe

```php
'key' => env('APP_KEY'),
'password' => env('DB_PASSWORD'),
```

Laravel's `env()` reads from `.env`, which must be
gitignored. Never commit `.env` files.

## Connection strings

### Vulnerable

```php
$dsn = "mysql:host=db.example.com;dbname=app";
$pdo = new PDO($dsn, 'root', 'hunter2');
```

### Safe

```php
$pdo = new PDO(
    env('DB_DSN'),
    env('DB_USERNAME'),
    env('DB_PASSWORD')
);
```

## WordPress wp-config

### Vulnerable

```php
define('DB_PASSWORD', 'production_password_here');
define('AUTH_KEY', 'put your unique phrase here');
```

### Safe

```php
define('DB_PASSWORD', getenv('WP_DB_PASSWORD'));
```
