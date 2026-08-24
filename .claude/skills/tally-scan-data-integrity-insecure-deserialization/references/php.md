# PHP insecure deserialization patterns

Vulnerable-vs-safe snippets for the PHP libraries and frameworks the
`data_integrity.insecure_deserialization` scanner recognizes.

## unserialize()

### Vulnerable

```php
$data = $_POST['object'];
$obj = unserialize($data);

$cookie = $_COOKIE['user'];
$user = unserialize($cookie);

$row = $db->query("SELECT data FROM cache WHERE id = 1")->fetch();
$obj = unserialize($row['data']);
```

### Safe

```php
$data = $_POST['object'];
$obj = unserialize($data, ['allowed_classes' => false]);

$cookie = $_COOKIE['user'];
$user = json_decode($cookie, true);

$row = $db->query("SELECT data FROM cache WHERE id = 1")->fetch();
$obj = unserialize($row['data'], ['allowed_classes' => false]);
```

`unserialize()` triggers `__wakeup`, `__destruct`, and `__toString` magic
methods during deserialization. Gadget chains in the application's class
hierarchy can be chained to reach file operations or code execution. Always
pass `['allowed_classes' => false]` to prevent object instantiation. Better,
use `json_decode()` for data exchange.

## Object injection via magic methods

### Vulnerable

```php
class Logger {
    public function __destruct() {
        file_put_contents($this->file, $this->message);
    }
}

class TemplateRenderer {
    public function __toString() {
        return eval($this->template);
    }
}

$data = $_GET['payload'];
$obj = unserialize($data);
```

### Safe

```php
class Logger {
    public function __destruct() {
        if (is_string($this->file) && is_string($this->message)) {
            file_put_contents($this->file, $this->message);
        }
    }
}

$data = $_GET['payload'];
$obj = unserialize($data, ['allowed_classes' => false]);
```

Gadget chains connect objects through their magic methods. A carefully crafted
serialized payload can instantiate objects with attacker-controlled properties
and trigger a chain of `__toString`, `__destruct`, and other handlers that
reach a dangerous sink. The safest approach is to never instantiate untrusted
objects. Use `['allowed_classes' => false]` or prefer JSON.

## Laravel serialized sessions and cookies

### Vulnerable

```php
use Illuminate\Support\Facades\Cookie;

$session = unserialize($_COOKIE['LARAVEL_SESSION']);

Cookie::queue('user', unserialize($request->cookie('user')));
```

### Safe

```php
use Illuminate\Support\Facades\Cookie;

$session = json_decode($_COOKIE['LARAVEL_SESSION'], true);

$user = $request->cookie('user');
```

In modern Laravel (5.1+), sessions are encrypted; the framework handles
serialization and validation. If you manually call `unserialize()` on a
cookie or session value, you bypass that protection. Rely on Laravel's
session API instead; if you must store custom data, use JSON.

## WordPress and direct unserialize

### Vulnerable

```php
$data = get_post_meta($post_id, 'custom_data', true);
$obj = unserialize($data);

$setting = get_option('plugin_setting');
$config = unserialize($setting);
```

### Safe

```php
$data = get_post_meta($post_id, 'custom_data', true);
$obj = maybe_unserialize($data);

$setting = get_option('plugin_setting');
$config = json_decode($setting, true);
```

WordPress provides `maybe_unserialize()`, which only unserializes if the
string is actually serialized. For options and metadata, WordPress also
offers `maybe_serialize()` and `json_encode()` alternatives. Avoid direct
`unserialize()` calls on data loaded from the database.
