# PHP SQL injection patterns

Vulnerable-vs-safe snippets for the PHP DB drivers and frameworks
the `injection.sql` scanner recognizes.

## PDO

### Vulnerable

```php
$id = $_GET['id'];
$stmt = $pdo->query("SELECT * FROM users WHERE id = $id");
$rows = $pdo->query("SELECT * FROM users WHERE email = '{$email}'");
```

### Safe

```php
$stmt = $pdo->prepare("SELECT * FROM users WHERE id = ?");
$stmt->execute([$id]);
$rows = $stmt->fetchAll();

$stmt = $pdo->prepare(
    "SELECT * FROM users WHERE email = :email"
);
$stmt->execute(['email' => $email]);
```

PDO supports positional `?` and named `:name` placeholders. Never
call `PDO::query` with a string that contains user data.

## mysqli

### Vulnerable

```php
$id = $_GET['id'];
$result = mysqli_query(
    $conn,
    "SELECT * FROM users WHERE id = $id"
);
```

### Safe

```php
$stmt = mysqli_prepare(
    $conn,
    "SELECT * FROM users WHERE id = ?"
);
mysqli_stmt_bind_param($stmt, "i", $id);
mysqli_stmt_execute($stmt);
$result = mysqli_stmt_get_result($stmt);
```

The second argument to `bind_param` is a type string:
`i` (int), `s` (string), `d` (double), `b` (blob).

## Laravel Eloquent

### Vulnerable

```php
$user = User::whereRaw("id = " . $request->id)->first();
$rows = DB::select("SELECT * FROM users WHERE id = " . $id);
$sorted = User::orderByRaw($request->sort)->get();
```

### Safe

```php
$user = User::where('id', $request->id)->first();
$rows = DB::select(
    "SELECT * FROM users WHERE id = ?",
    [$id]
);
$user = User::whereRaw('id = ?', [$request->id])->first();
```

Eloquent's `where`, `whereIn`, `whereBetween` parameterize by
default. When raw SQL is truly needed, the second argument is a
bindings array.

For dynamic sort columns, validate against an allowlist:

```php
$allowed = ['name', 'created_at', 'updated_at'];
$sort = in_array($request->sort, $allowed) ? $request->sort : 'name';
$users = User::orderBy($sort)->get();
```

## WordPress `$wpdb`

### Vulnerable

```php
$id = $_GET['id'];
$row = $wpdb->get_row("SELECT * FROM {$wpdb->users} WHERE ID = $id");
$rows = $wpdb->get_results(
    "SELECT * FROM {$wpdb->posts} WHERE post_status = '{$status}'"
);
```

### Safe

```php
$row = $wpdb->get_row(
    $wpdb->prepare(
        "SELECT * FROM {$wpdb->users} WHERE ID = %d",
        $id
    )
);

$rows = $wpdb->get_results(
    $wpdb->prepare(
        "SELECT * FROM {$wpdb->posts} WHERE post_status = %s",
        $status
    )
);
```

`$wpdb->prepare` placeholders: `%d` (int), `%s` (string, single-
quoted for you), `%f` (float). The table-name interpolation
(`{$wpdb->posts}`) is safe because table names come from WordPress
core, not from request data.

## Doctrine DBAL

### Vulnerable

```php
$rows = $conn->executeQuery(
    "SELECT * FROM users WHERE id = $id"
);
```

### Safe

```php
$rows = $conn->executeQuery(
    "SELECT * FROM users WHERE id = ?",
    [$id]
);

$rows = $conn->executeQuery(
    "SELECT * FROM users WHERE email = :email",
    ['email' => $email]
);
```

Doctrine's QueryBuilder is the higher-level safe alternative:

```php
$rows = $conn->createQueryBuilder()
    ->select('*')
    ->from('users')
    ->where('id = :id')
    ->setParameter('id', $id)
    ->executeQuery()
    ->fetchAllAssociative();
```

## Dynamic table or column names

Placeholders cover values, not identifiers. Validate identifier
strings against an allowlist:

```php
$allowed = ['name', 'email', 'created_at'];
if (!in_array($sort_col, $allowed, true)) {
    throw new InvalidArgumentException("Invalid sort column");
}
$rows = $pdo->query(
    "SELECT * FROM users ORDER BY {$sort_col} LIMIT 100"
)->fetchAll();
```

The allowlist is the safety measure; the interpolation is safe
only because `$sort_col` is guaranteed to be a known column.
