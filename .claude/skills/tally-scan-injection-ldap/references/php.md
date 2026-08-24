# PHP LDAP injection patterns

Vulnerable-vs-safe snippets for the PHP LDAP extension the `injection.ldap`
scanner recognizes. When multiple safe forms exist, the canonical one is
shown first.

## ldap_search() and related functions

### Vulnerable

```php
$user_id = $_GET['uid'];
$filter = "(uid=$user_id)";
ldap_search($conn, "dc=example,dc=com", $filter);
```

```php
$email = $_POST['email'];
$filter = "(mail=" . $email . ")";
ldap_search($conn, $base, $filter);
```

```php
$user_id = $_GET['uid'];
$filter = sprintf("(uid=%s)", $user_id);
ldap_search($conn, $base, $filter);
```

### Safe

```php
$user_id = $_GET['uid'];
$escaped_id = ldap_escape($user_id, '', LDAP_ESCAPE_FILTER);
$filter = "(uid=$escaped_id)";
ldap_search($conn, "dc=example,dc=com", $filter);
```

```php
$email = $_POST['email'];
$escaped_email = ldap_escape($email, '', LDAP_ESCAPE_FILTER);
$filter = "(mail=" . $escaped_email . ")";
ldap_search($conn, $base, $filter);
```

```php
$user_id = $_GET['uid'];
$escaped_id = ldap_escape($user_id, '', LDAP_ESCAPE_FILTER);
$filter = sprintf("(uid=%s)", $escaped_id);
ldap_search($conn, $base, $filter);
```

`ldap_escape()` with the `LDAP_ESCAPE_FILTER` flag removes special
characters that have meaning in LDAP filters (parentheses, asterisks,
backslashes, null bytes, etc.). Always escape request-derived values before
building the filter string.

The third argument (empty string `''`) applies the escape to the filter
context. The fourth argument specifies the escape context; use
`LDAP_ESCAPE_FILTER` for filter strings and `LDAP_ESCAPE_DN` for
distinguished names.

## ldap_list() and ldap_read()

### Vulnerable

```php
$cn = $_GET['cn'];
ldap_list($conn, "dc=example,dc=com", "(cn=$cn)");
```

### Safe

```php
$cn = $_GET['cn'];
$escaped_cn = ldap_escape($cn, '', LDAP_ESCAPE_FILTER);
ldap_list($conn, "dc=example,dc=com", "(cn=$escaped_cn)");
```

The same escaping rule applies to `ldap_list()`, `ldap_read()`, and all
other functions that accept a filter argument. Always use `ldap_escape()`.

## Complex filters with logical operators

### Vulnerable

```php
$uid = $_GET['uid'];
$mail = $_GET['mail'];
$filter = "(&(uid=$uid)(mail=$mail))";
ldap_search($conn, $base, $filter);
```

### Safe

```php
$uid = $_GET['uid'];
$mail = $_GET['mail'];
$escaped_uid = ldap_escape($uid, '', LDAP_ESCAPE_FILTER);
$escaped_mail = ldap_escape($mail, '', LDAP_ESCAPE_FILTER);
$filter = "(&(uid=$escaped_uid)(mail=$escaped_mail))";
ldap_search($conn, $base, $filter);
```

Escape every variable component, even in complex filters with AND (`&`),
OR (`|`), and NOT (`!`) operators.
