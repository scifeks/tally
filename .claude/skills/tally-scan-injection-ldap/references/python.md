# Python LDAP injection patterns

Vulnerable-vs-safe snippets for the Python LDAP libraries the
`injection.ldap` scanner recognizes. When multiple safe forms exist,
the canonical one is shown first.

## python-ldap

### Vulnerable

```python
user_id = request.args.get("uid")
conn = ldap.open("ldap://ldap.example.com")
results = conn.search_s(
    "dc=example,dc=com",
    ldap.SCOPE_SUBTREE,
    f"(uid={user_id})",
)
```

```python
username = request.form.get("username")
filter_str = "(uid=" + username + ")"
conn.search_s(base, ldap.SCOPE_SUBTREE, filter_str)
```

### Safe

```python
import ldap.filter

user_id = request.args.get("uid")
conn = ldap.open("ldap://ldap.example.com")
escaped_id = ldap.filter.escape_filter_chars(user_id)
results = conn.search_s(
    "dc=example,dc=com",
    ldap.SCOPE_SUBTREE,
    f"(uid={escaped_id})",
)
```

`python-ldap` provides `ldap.filter.escape_filter_chars()` to escape special
LDAP filter characters. Always escape request-derived values before building
the filter string.

## ldap3

### Vulnerable

```python
from ldap3 import Server, Connection

user_id = request.args.get("uid")
server = Server("ldap://ldap.example.com")
conn = Connection(server)
conn.bind()

conn.search(
    "dc=example,dc=com",
    f"(uid={user_id})",
)
```

```python
conn.search(
    base,
    "(uid=" + user_id + ")",
)
```

### Safe

```python
from ldap3 import Server, Connection
from ldap3.utils import escape_filter_chars

user_id = request.args.get("uid")
server = Server("ldap://ldap.example.com")
conn = Connection(server)
conn.bind()

escaped_id = escape_filter_chars(user_id)
conn.search(
    "dc=example,dc=com",
    f"(uid={escaped_id})",
)
```

```python
conn.search(
    base,
    "(uid=" + escape_filter_chars(user_id) + ")",
)
```

`ldap3` provides `ldap3.utils.escape_filter_chars()`. Import it and apply it
to every request-derived value before interpolating into the filter. For
dynamic DN components (the `rdn` argument to `search()`), use
`escape_rdn()` instead.

## Using filter_format() for complex filters

For filters with multiple placeholders, `ldap3` offers a safer API:

```python
from ldap3 import Server, Connection

user_id = request.args.get("uid")
email = request.args.get("email")
server = Server("ldap://ldap.example.com")
conn = Connection(server)
conn.bind()

# Internally escapes all placeholders
conn.search(
    "dc=example,dc=com",
    "(&(uid={user})(mail={email}))",
    {"user": user_id, "email": email},
)
```

The filter string contains `{name}` placeholders; pass a dict of values as
the third argument. `ldap3` automatically escapes all values. This is the
preferred approach for complex filters.
