# PHP file upload patterns

Vulnerable-vs-safe snippets for the PHP frameworks and native handlers
the `data_integrity.file_upload` scanner recognizes.

## Native $_FILES + move_uploaded_file

### Vulnerable

```php
<?php
$upload_dir = 'uploads/';
$file = $_FILES['photo'];
$target = $upload_dir . basename($file['name']);
move_uploaded_file($file['tmp_name'], $target);
echo "File uploaded";
?>
```

### Safe

```php
<?php
$upload_dir = 'uploads/';
$allowed_extensions = ['jpg', 'jpeg', 'png', 'gif', 'txt'];
$allowed_mimes = [
    'image/jpeg', 'image/png', 'image/gif', 'text/plain'
];

$file = $_FILES['photo'];
$filename = basename($file['name']);

if (strpos($filename, '.') === false) {
    die('No file extension');
}
$ext = strtolower(pathinfo($filename, PATHINFO_EXTENSION));
if (!in_array($ext, $allowed_extensions, true)) {
    die('File type not allowed');
}

$finfo = finfo_open(FILEINFO_MIME_TYPE);
$mime = finfo_file($finfo, $file['tmp_name']);
finfo_close($finfo);
if (!in_array($mime, $allowed_mimes, true)) {
    die('File content type not allowed');
}

$target = $upload_dir . preg_replace(
    '/[^a-zA-Z0-9._-]/',
    '',
    $filename
);
if (!move_uploaded_file($file['tmp_name'], $target)) {
    die('Upload failed');
}
?>
```

Never trust `$_FILES['type']` because the client controls it. Always verify
the extension against an allowlist and check the actual MIME type with
`finfo_file()` on the temp file. Sanitize the filename to prevent directory
traversal.

## Laravel

### Vulnerable

```php
class PhotoController {
    public function store(Request $request) {
        $file = $request->file('photo');
        $path = $file->store('photos');
        return redirect()->back();
    }
}
```

### Safe

```php
class PhotoController {
    public function store(Request $request) {
        $request->validate([
            'photo' => 'required|file|mimes:jpeg,png,gif|max:2048'
        ]);
        $file = $request->file('photo');
        $path = $file->store('photos');
        return redirect()->back();
    }
}
```

Add a `validate()` call with the `mimes` rule, which checks the file's
actual content, not only the extension. The `max:2048` constraint caps the
file size in kilobytes. Laravel's `mimes` rule uses `finfo_file` internally
to verify the MIME type.

## Symfony

### Vulnerable

```php
public function upload(Request $request): Response {
    $file = $request->files->get('photo');
    $filename = $file->getClientOriginalName();
    $file->move('public/uploads', $filename);
    return new Response('Uploaded');
}
```

### Safe

```php
public function upload(Request $request): Response {
    $file = $request->files->get('photo');
    $filename = $file->getClientOriginalName();

    $allowed = ['jpg', 'jpeg', 'png', 'gif', 'txt'];
    $ext = strtolower(
        pathinfo($filename, PATHINFO_EXTENSION)
    );
    if (!in_array($ext, $allowed, true)) {
        throw new BadRequestHttpException(
            'File type not allowed'
        );
    }

    $guessed = $file->guessExtension();
    if ($guessed === null) {
        throw new BadRequestHttpException(
            'Cannot determine file type'
        );
    }

    $safeFilename = bin2hex(random_bytes(16)) . '.' . $guessed;
    $file->move('public/uploads', $safeFilename);
    return new Response('Uploaded');
}
```

Validate the extension against an allowlist. Use `guessExtension()` to
verify the MIME type based on file content, not the client-provided
extension. Generate a random safe filename to prevent directory traversal
and filename collisions.

## WordPress

### Vulnerable

```php
<?php
if ($_FILES['file']['error'] === UPLOAD_ERR_OK) {
    $filename = $_FILES['file']['name'];
    $upload_dir = wp_upload_dir();
    $target = $upload_dir['path'] . '/' . $filename;
    move_uploaded_file($_FILES['file']['tmp_name'], $target);
}
?>
```

### Safe

```php
<?php
$allowed_types = ['image/jpeg', 'image/png', 'image/gif'];
$max_size = 2 * 1024 * 1024; // 2 MB

if ($_FILES['file']['error'] === UPLOAD_ERR_OK) {
    $filename = $_FILES['file']['name'];
    $ext = strtolower(pathinfo($filename, PATHINFO_EXTENSION));
    if (!in_array($ext, ['jpg', 'jpeg', 'png', 'gif'], true)) {
        wp_die('File type not allowed');
    }

    if ($_FILES['file']['size'] > $max_size) {
        wp_die('File too large');
    }

    $finfo = finfo_open(FILEINFO_MIME_TYPE);
    $mime = finfo_file($finfo, $_FILES['file']['tmp_name']);
    finfo_close($finfo);
    if (!in_array($mime, $allowed_types, true)) {
        wp_die('File content type not allowed');
    }

    $upload_dir = wp_upload_dir();
    $filename = wp_unique_filename(
        $upload_dir['path'],
        $filename
    );
    $target = $upload_dir['path'] . '/' . $filename;
    move_uploaded_file($_FILES['file']['tmp_name'], $target);
}
?>
```

Validate the extension and file size before upload. Use `finfo_file()` to
check the actual MIME type. Use `wp_unique_filename()` to generate a safe
filename that avoids collisions and directory traversal.
