# PHP race condition patterns

Vulnerable-vs-safe snippets for the PHP concurrent operations the
`design_logic.race_condition` scanner recognizes.

## Session data race condition

### Vulnerable

```php
<?php
session_start();

$_SESSION['balance'] = $_SESSION['balance'] - $amount;
$_SESSION['last_update'] = time();

// Another concurrent request can modify $_SESSION here
```

### Safe

```php
<?php
session_start();
session_write_close();

$balance = $_SESSION['balance'];
$balance -= $amount;

session_start();
$_SESSION['balance'] = $balance;
$_SESSION['last_update'] = time();
session_write_close();
```

Call `session_write_close()` before long operations to release the session
lock, then restart the session for final writes. Alternatively, use Redis or
Memcached for session storage with explicit locking.

## Database operations without transaction

### Vulnerable

```php
<?php
$db = new PDO("sqlite::memory:");

$stmt = $db->prepare("SELECT balance FROM users WHERE id = ?");
$stmt->execute([$user_id]);
$row = $stmt->fetch();
$balance = $row['balance'];

if ($balance >= $amount) {
    $stmt = $db->prepare("UPDATE users SET balance = balance - ? WHERE id = ?");
    $stmt->execute([$amount, $user_id]);
}
```

### Safe

```php
<?php
$db = new PDO("sqlite::memory:");
$db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);

try {
    $db->beginTransaction();
    
    $stmt = $db->prepare("SELECT balance FROM users WHERE id = ? FOR UPDATE");
    $stmt->execute([$user_id]);
    $row = $stmt->fetch();
    
    if ($row && $row['balance'] >= $amount) {
        $stmt = $db->prepare("UPDATE users SET balance = balance - ? WHERE id = ?");
        $stmt->execute([$amount, $user_id]);
        $db->commit();
        return true;
    } else {
        $db->rollBack();
        return false;
    }
} catch (Exception $e) {
    $db->rollBack();
    throw $e;
}
```

Wrap the check and update in a `beginTransaction()` block and use SELECT ...
FOR UPDATE to lock the row during the read-modify-write sequence.

## File-based counter without locking

### Vulnerable

```php
<?php
$counter_file = '/tmp/counter.txt';

function increment_counter() {
    global $counter_file;
    $count = file_get_contents($counter_file);
    $count = intval($count) + 1;
    file_put_contents($counter_file, $count);
}

increment_counter();
```

### Safe

```php
<?php
$counter_file = '/tmp/counter.txt';

function increment_counter() {
    global $counter_file;
    $handle = fopen($counter_file, 'r+');
    if (flock($handle, LOCK_EX)) {
        try {
            $count = fread($handle, filesize($counter_file));
            $count = intval($count) + 1;
            
            fseek($handle, 0);
            ftruncate($handle, 0);
            fwrite($handle, $count);
        } finally {
            flock($handle, LOCK_UN);
        }
    }
    fclose($handle);
}

increment_counter();
```

Use `flock($handle, LOCK_EX)` to acquire an exclusive lock on the file
before reading and writing. Hold the lock until the read-modify-write
sequence completes.

## Shared memory without synchronization

### Vulnerable

```php
<?php
$shm_id = shmop_open(0x1234, "a", 0, 1024);
$data = shmop_read($shm_id, 0, 100);

$count = intval($data) + 1;
shmop_write($shm_id, (string)$count, 0);
shmop_close($shm_id);
```

### Safe

```php
<?php
$sem_id = sem_get(0x1234, 1);
$shm_id = shmop_open(0x1234, "a", 0, 1024);

if (sem_acquire($sem_id)) {
    try {
        $data = shmop_read($shm_id, 0, 100);
        $count = intval($data) + 1;
        shmop_write($shm_id, (string)$count, 0);
    } finally {
        sem_release($sem_id);
    }
}

shmop_close($shm_id);
```

Use `sem_get()` and `sem_acquire()` to protect access to shared memory
segments. Release the semaphore after the read-modify-write sequence.

## Database unique constraint race

### Vulnerable

```php
<?php
$db = new PDO("mysql:host=localhost;dbname=app");

$stmt = $db->prepare("SELECT id FROM users WHERE email = ?");
$stmt->execute([$email]);

if ($stmt->rowCount() === 0) {
    $stmt = $db->prepare("INSERT INTO users (email, name) VALUES (?, ?)");
    $stmt->execute([$email, $name]);
}
```

### Safe (Option 1: INSERT ... ON DUPLICATE KEY)

```php
<?php
$db = new PDO("mysql:host=localhost;dbname=app");

$stmt = $db->prepare(
    "INSERT INTO users (email, name) VALUES (?, ?) " .
    "ON DUPLICATE KEY UPDATE name = VALUES(name)"
);
$stmt->execute([$email, $name]);
```

### Safe (Option 2: Unique constraint with error handling)

```php
<?php
$db = new PDO("mysql:host=localhost;dbname=app");

try {
    $stmt = $db->prepare("INSERT INTO users (email, name) VALUES (?, ?)");
    $stmt->execute([$email, $name]);
} catch (PDOException $e) {
    if (strpos($e->getMessage(), 'Duplicate entry') !== false) {
        $stmt = $db->prepare("UPDATE users SET name = ? WHERE email = ?");
        $stmt->execute([$name, $email]);
    } else {
        throw $e;
    }
}
```

Use INSERT ... ON DUPLICATE KEY UPDATE to make the insert-or-update atomic,
or rely on database constraints and handle the exception.
