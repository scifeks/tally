# PHP NoSQL injection patterns

Vulnerable-vs-safe snippets for the PHP NoSQL libraries the
`injection.nosql` scanner recognizes. When multiple safe forms exist, the
canonical one is shown first.

## ext-mongodb (native driver)

### Operator injection (vulnerable)

```php
$userId = json_decode($_POST['user_id'], true);
$result = $collection->find(["user" => $userId]);
```

If `$_POST['user_id']` is `{"$gt": ""}`, the query becomes `["user" =>
["$gt" => ""]]`, matching all documents.

```php
$body = json_decode(file_get_contents('php://input'), true);
$collection->insertOne($body);
```

Attacker sends `{"$set": {"role": "admin"}}` and modifies document
insertion behavior.

### Operator injection (safe)

```php
$userId = (string)$_POST['user_id'];
$result = $collection->find(["user" => $userId]);
```

Cast to scalar type to prevent operator injection.

```php
$body = json_decode(file_get_contents('php://input'), true);
$collection->insertOne([
    "username" => (string)$body["username"],
    "email" => (string)$body["email"],
]);
```

Explicitly extract and type-cast fields from decoded input.

### $where injection (vulnerable)

```php
$name = $_GET['name'];
$result = $collection->find(['$where' => "this.name == '$name'"]);
```

User input reaches JavaScript evaluation on the server. Attacker can
inject `'; return true; //`.

### $where injection (safe)

```php
$name = $_GET['name'];
$result = $collection->find(['name' => $name]);
```

Use query operators instead of `$where`.

## Doctrine ODM

### Vulnerable with query builder

```php
$body = json_decode($_POST['data'], true);
$qb = $dm->createQueryBuilder('User');
$qb->field($body['field'])->equals($body['value']);
$result = $qb->getQuery()->execute();
```

If `$body['field']` is injected as `$set`, it can modify unexpected
fields.

### Safe with query builder

```php
$body = json_decode($_POST['data'], true);
$ALLOWED_FIELDS = ['username', 'email', 'status'];
$field = $body['field'];
if (!in_array($field, $ALLOWED_FIELDS, true)) {
    throw new InvalidArgumentException("Invalid field");
}
$value = (string)$body['value'];
$qb = $dm->createQueryBuilder('User');
$qb->field($field)->equals($value);
$result = $qb->getQuery()->execute();
```

Whitelist allowed fields and cast values to scalars.

### Vulnerable with array merge

```php
$baseFilter = ['status' => 'active'];
$userFilter = json_decode($_GET['filter'], true);
$filter = array_merge($baseFilter, $userFilter);
$collection->find($filter);
```

User-supplied keys in the filter can inject operators.

### Safe with array merge

```php
$baseFilter = ['status' => 'active'];
$ALLOWED_FIELDS = ['username', 'email'];
$userFilter = json_decode($_GET['filter'], true);
$safe = [];
foreach ($userFilter as $key => $value) {
    if (in_array($key, $ALLOWED_FIELDS, true)) {
        $safe[$key] = (string)$value;
    }
}
$filter = array_merge($baseFilter, $safe);
$collection->find($filter);
```

Sanitize keys and values from user input before merging.

## Preventing operator injection: mongodb-php-library sanitization

Use `mongodb\BSON\Serializable` or explicit type casting:

```php
$body = json_decode(file_get_contents('php://input'), true);
$document = new stdClass();
$document->username = (string)($body['username'] ?? '');
$document->email = (string)($body['email'] ?? '');
$collection->insertOne((array)$document);
```

Or strip keys starting with `$`:

```php
function sanitizeOperators($array) {
    $result = [];
    foreach ($array as $key => $value) {
        if (strpos($key, '$') !== 0 && strpos($key, '.') !== 0) {
            $result[$key] = is_array($value) ? sanitizeOperators($value) : $value;
        }
    }
    return $result;
}

$body = json_decode($_POST['data'], true);
$collection->insertOne(sanitizeOperators($body));
```
