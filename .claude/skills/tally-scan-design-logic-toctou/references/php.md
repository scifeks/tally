# PHP TOCTOU race condition patterns

Vulnerable-vs-safe snippets for the PHP file and database operations the
`design_logic.toctou` scanner recognizes.

## Native filesystem operations (fopen, file_get_contents)

### Vulnerable

```php
$user_file = $_GET['file'];
if (file_exists($user_file)) {
    $content = file_get_contents($user_file);
    echo $content;
}

$config = '/tmp/config.json';
if (is_writable(dirname($config))) {
    file_put_contents($config, $json_data);
}

$path = $_SERVER['UPLOAD_DIR'] . '/' . $filename;
if (!file_exists($path)) {
    $fh = fopen($path, 'w');
    fwrite($fh, $data);
    fclose($fh);
}
```

### Safe

```php
$user_file = $_GET['file'];
try {
    $content = file_get_contents($user_file);
    echo $content;
} catch (Throwable $e) {
    error_log("Failed to read file: " . $e->getMessage());
}

$config = '/tmp/config.json';
try {
    file_put_contents($config, $json_data);
} catch (Throwable $e) {
    error_log("Write failed: " . $e->getMessage());
}

$path = $_SERVER['UPLOAD_DIR'] . '/' . $filename;
$fh = fopen($path, 'wx');
if ($fh) {
    fwrite($fh, $data);
    fclose($fh);
} else {
    error_log("File already exists or create failed");
}
```

Eliminate the check-then-use pattern. For exclusive creation, use `fopen(
$path, 'wx')`, which fails if the file exists. For reads and writes,
handle errors at the point of use instead of checking beforehand.

## File locking with flock

### Vulnerable

```php
function update_config($data) {
    $config_file = '/etc/app/config.json';
    if (is_writable($config_file)) {
        file_put_contents($config_file, json_encode($data));
    }
}
```

### Safe

```php
function update_config($data) {
    $config_file = '/etc/app/config.json';
    $fh = fopen($config_file, 'c+');
    if (flock($fh, LOCK_EX)) {
        ftruncate($fh, 0);
        rewind($fh);
        fwrite($fh, json_encode($data));
        fflush($fh);
        flock($fh, LOCK_UN);
    }
    fclose($fh);
}
```

`flock($handle, LOCK_EX)` acquires an exclusive lock on the file. The lock
prevents other processes from reading or writing the file while the lock is
held. Always unlock with `LOCK_UN` and close the handle.

## PDO transactions with SELECT FOR UPDATE

### Vulnerable

```php
$email = $_POST['email'];
$stmt = $pdo->query("SELECT id FROM users WHERE email = '$email'");
if ($stmt->rowCount() === 0) {
    $insert = $pdo->prepare("INSERT INTO users (email) VALUES (?)");
    $insert->execute([$email]);
    $user_id = $pdo->lastInsertId();
} else {
    $row = $stmt->fetch();
    $user_id = $row['id'];
}
```

### Safe

```php
$email = $_POST['email'];
try {
    $pdo->beginTransaction();
    $stmt = $pdo->prepare(
        "SELECT id FROM users WHERE email = ? FOR UPDATE"
    );
    $stmt->execute([$email]);
    if ($stmt->rowCount() === 0) {
        $insert = $pdo->prepare("INSERT INTO users (email) VALUES (?)");
        $insert->execute([$email]);
        $user_id = $pdo->lastInsertId();
    } else {
        $row = $stmt->fetch();
        $user_id = $row['id'];
    }
    $pdo->commit();
} catch (Exception $e) {
    $pdo->rollBack();
    throw $e;
}
```

`SELECT ... FOR UPDATE` locks the matching rows until the transaction
commits. This prevents another connection from inserting or updating the
same rows during the transaction.

## PDO INSERT ... ON DUPLICATE KEY UPDATE

### Vulnerable

```php
$email = $_POST['email'];
$stmt = $pdo->query("SELECT id FROM users WHERE email = '$email'");
if ($stmt->rowCount() === 0) {
    $pdo->query("INSERT INTO users (email) VALUES ('$email')");
}
```

### Safe

```php
$email = $_POST['email'];
$stmt = $pdo->prepare(
    "INSERT INTO users (email, created_at) VALUES (?, NOW())
     ON DUPLICATE KEY UPDATE updated_at = NOW()"
);
$stmt->execute([$email]);
```

`INSERT ... ON DUPLICATE KEY UPDATE` is an atomic operation. The database
engine checks for duplicates and inserts or updates in a single operation,
closing the race window.

## Laravel Eloquent findOrCreate

### Vulnerable

```php
$email = $request->email;
if (!User::where('email', $email)->exists()) {
    $user = User::create(['email' => $email]);
} else {
    $user = User::where('email', $email)->first();
}
```

### Safe

```php
$email = $request->email;
$user = User::firstOrCreate(
    ['email' => $email],
    ['name' => $request->name]
);
```

`firstOrCreate()` is atomic. It uses INSERT ... ON DUPLICATE KEY UPDATE
internally, eliminating the race between the check and the insert.

## Database balance/quota atomicity

### Vulnerable

```php
$user_id = $_POST['user_id'];
$amount = $_POST['amount'];
$user = User::find($user_id);
if ($user->balance >= $amount) {
    $user->balance -= $amount;
    $user->save();
}
```

### Safe

```php
$user_id = $_POST['user_id'];
$amount = $_POST['amount'];
$stmt = $pdo->prepare(
    "UPDATE users SET balance = balance - ? WHERE id = ? AND balance >= ?"
);
$stmt->execute([$amount, $user_id, $amount]);
if ($stmt->rowCount() === 0) {
    throw new Exception("Insufficient balance");
}
```

Perform the check and the debit in a single atomic UPDATE statement. Check
the affected row count; if zero rows were affected, the balance was
insufficient or the user does not exist.
