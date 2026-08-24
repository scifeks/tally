# PHP path traversal patterns

Vulnerable-vs-safe snippets for the PHP file operations and frameworks
the `access_control.path_traversal` scanner recognizes. When multiple
safe forms exist, the canonical one is shown first.

## file_get_contents / fopen

### Vulnerable

```php
$file = $_GET['file'];
$content = file_get_contents('/uploads/' . $file);
echo $content;

$path = '/var/www/static/' . $_POST['document'];
$handle = fopen($path, 'r');
```

### Safe

```php
$file = $_GET['file'];
$base = '/uploads';
$real_base = realpath($base);
$filepath = realpath($base . '/' . $file);
if ($filepath === false ||
    strpos($filepath, $real_base) !== 0) {
    abort(403);
}
$content = file_get_contents($filepath);
echo $content;

// or use basename to strip directory components
$file = basename($_GET['file']);
$filepath = '/uploads/' . $file;
$content = file_get_contents($filepath);
```

Always call `realpath` and verify the result with `strpos` to confirm
the path stays within the base directory.

## readfile

### Vulnerable

```php
$filename = $_GET['name'];
readfile('/data/' . $filename);
```

### Safe

```php
$filename = $_GET['name'];
$base = '/data';
$real_base = realpath($base);
$filepath = realpath($base . '/' . $filename);
if ($filepath === false ||
    strpos($filepath, $real_base) !== 0) {
    http_response_code(403);
    return;
}
readfile($filepath);

// or
$filename = basename($_GET['name']);
readfile('/data/' . $filename);
```

Use `realpath` to resolve the full path and verify it starts with the
base directory.

## include / require

### Vulnerable

```php
$template = $_GET['template'];
include('/app/templates/' . $template);

$controller = $_REQUEST['page'];
require("pages/" . $controller . ".php");
```

### Safe

```php
$template = $_GET['template'];
$allowed = ['home', 'about', 'contact'];
if (!in_array($template, $allowed)) {
    abort(403);
}
include('/app/templates/' . $template . '.php');

// or validate path
$base = realpath('/app/templates');
$requested = realpath('/app/templates/' . $template);
if ($requested === false ||
    strpos($requested, $base) !== 0) {
    abort(403);
}
include($requested);
```

Use an allowlist of template names or validate the resolved path stays
within the template directory.

## Laravel Storage

### Vulnerable

```php
$filename = request()->input('path');
$content = Storage::get($filename);
return response($content);
```

### Safe

```php
$filename = request()->input('path');
$allowed_files = ['config.json', 'settings.yml'];
if (!in_array($filename, $allowed_files)) {
    abort(403);
}
$content = Storage::get($filename);
return response($content);

// or validate the path
$filename = request()->input('path');
$path = storage_path('app/' . $filename);
$base = storage_path('app');
if (!str_starts_with(
    realpath($path) ?: '', realpath($base) ?: ''
)) {
    abort(403);
}
$content = Storage::get($filename);
```

Use an allowlist or validate the resolved path stays within the
storage directory.

## WordPress $wpdb

### Vulnerable

```php
$file_id = $_GET['id'];
$query = "SELECT path FROM files WHERE id = $file_id";
$file = $wpdb->get_row($query);
readfile(WP_CONTENT_DIR . '/' . $file->path);
```

### Safe

```php
$file_id = intval($_GET['id']);
$file = $wpdb->get_row(
    $wpdb->prepare("SELECT path FROM files WHERE id = %d",
        $file_id)
);
$base = WP_CONTENT_DIR;
$real_base = realpath($base);
$filepath = realpath($base . '/' . $file->path);
if ($filepath === false ||
    strpos($filepath, $real_base) !== 0) {
    wp_die('Access denied');
}
readfile($filepath);
```

Always validate the resolved path with `realpath` and `strpos`, even
when the path comes from the database, to defend against database
compromise.

## Common patterns

For any file operation in PHP, the safe pattern is:

```php
$base = realpath($base_directory);
$full_path = realpath($base . DIRECTORY_SEPARATOR . $user_input);
if ($full_path === false ||
    strpos($full_path, $base . DIRECTORY_SEPARATOR) !== 0) {
    abort(403);
}
// now use $full_path safely
```

Or use an allowlist of permitted filenames if the set is small and
fixed.
