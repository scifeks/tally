# PHP file permissions patterns

Vulnerable-vs-safe snippets for insecure file permission operations the
`misconfig.insecure_file_permissions` scanner recognizes. When multiple
safe forms exist, the canonical one is shown first.

## chmod with overly permissive mode

### Vulnerable

```php
<?php
// Credential file
chmod('secrets.txt', 0777);

// Config file
chmod('/etc/app/config.php', 0666);

// Or octal
chmod($key_file, 0777);
```

### Safe

```php
<?php
// Credential file: owner read/write only
chmod('secrets.txt', 0600);

// Config file: owner read/write, group read
chmod('/etc/app/config.php', 0640);

// Explicitly restrictive
chmod($key_file, 0600);
```

Never grant world-read or world-write permissions to credential, config, or
secret files. Use `0600` for owner-only access or `0640` for
owner-read/write and group-read access when shared with a specific group.

## file_put_contents without umask

### Vulnerable

```php
<?php
// Writing credentials without setting restrictive umask
file_put_contents('db_password.txt', $password);

// File inherits default umask permissions, likely world-readable
file_put_contents('api_keys.env', $api_keys);

// Config file written without permission control
file_put_contents('.env', $env_data);
```

### Safe

```php
<?php
// Set restrictive umask before writing
$old_umask = umask(0077);
try {
    file_put_contents('db_password.txt', $password);
} finally {
    umask($old_umask);
}

// Better: set permissions after writing
file_put_contents('db_password.txt', $password);
chmod('db_password.txt', 0600);

// For critical files: save, chmod, verify atomically
$temp_file = tempnam(sys_get_temp_dir(), 'tmp_');
file_put_contents($temp_file, $password);
chmod($temp_file, 0600);
rename($temp_file, 'db_password.txt');
```

Always set a restrictive umask (typically `0077`) before writing credential
or secret files, or explicitly set permissions to `0600` immediately after
writing.

## tmpfile() usage patterns

### Vulnerable

```php
<?php
// tmpfile() creates a file in system temp directory
$handle = tmpfile();
fwrite($handle, $sensitive_data);

// File permissions depend on system umask and temp directory; may be
// world-readable on some systems
```

### Safe

```php
<?php
// Use a temporary directory with explicit permissions
$temp_dir = sys_get_temp_dir();
$temp_file = tempnam($temp_dir, 'app_');
@chmod($temp_file, 0600);

$handle = fopen($temp_file, 'w');
fwrite($handle, $sensitive_data);
fclose($handle);

// Clean up after use
unlink($temp_file);

// Better: use a callback to ensure cleanup
function with_temp_file($callback) {
    $temp_file = tempnam(sys_get_temp_dir(), 'app_');
    @chmod($temp_file, 0600);
    try {
        return $callback($temp_file);
    } finally {
        unlink($temp_file);
    }
}

// Usage
with_temp_file(function($temp_file) {
    $handle = fopen($temp_file, 'w');
    fwrite($handle, $sensitive_data);
    fclose($handle);
});
```

Avoid relying on `tmpfile()` for sensitive data. Instead, use
`tempnam(sys_get_temp_dir(), 'app_')` and explicitly set permissions to
`0600` with `chmod()`. Always clean up temporary files after use.

## Config files written with permissive defaults

### Vulnerable

```php
<?php
// Writing .env file without permission control
file_put_contents('.env', "DB_PASSWORD={$db_pass}\n");

// Database credentials written insecurely
file_put_contents('config/database.php', $config_array);

// API keys saved to file
file_put_contents('keys.json', json_encode($api_keys));

// Or without setting umask
$config = serialize($app_config);
file_put_contents('config.php', $config);
```

### Safe

```php
<?php
// Set restrictive umask and write
$old_umask = umask(0077);
try {
    file_put_contents('.env', "DB_PASSWORD={$db_pass}\n");
} finally {
    umask($old_umask);
}

// Better: write then chmod
file_put_contents('.env', "DB_PASSWORD={$db_pass}\n");
chmod('.env', 0600);

// For secure atomic writes with permissions
$temp_file = tempnam(dirname('.env'), '.env_');
@chmod($temp_file, 0600);
file_put_contents($temp_file, "DB_PASSWORD={$db_pass}\n");
rename($temp_file, '.env');

// Using a config writer helper
function write_config_secure($path, $data) {
    $old_umask = umask(0077);
    try {
        file_put_contents($path, $data);
        chmod($path, 0600);
    } finally {
        umask($old_umask);
    }
}

write_config_secure('.env', "DB_PASSWORD={$db_pass}\n");
```

Always set a restrictive umask before writing configuration files, and
explicitly set permissions to `0600` immediately after. Consider atomic
write patterns (write to temp file, chmod, then rename) to avoid exposing
sensitive data during the write operation.
