# Python SQL injection patterns

Vulnerable-vs-safe snippets for the Python DB drivers and ORMs the
`injection.sql` scanner recognizes. When multiple safe forms exist,
the canonical one is shown first.

## sqlite3 (stdlib)

### Vulnerable

```python
user_id = request.args.get("id")
cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")
cursor.execute("SELECT * FROM users WHERE name = '%s'" % name)
cursor.execute("SELECT * FROM users WHERE id = " + str(user_id))
```

### Safe

```python
cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
cursor.execute(
    "SELECT * FROM users WHERE name = :name",
    {"name": name},
)
```

`sqlite3` uses `?` (positional) and `:name` (named) placeholders.
Never pass a formatted string.

## psycopg2 / psycopg

### Vulnerable

```python
cursor.execute(f"SELECT * FROM users WHERE email = '{email}'")
cursor.execute("... WHERE id IN (%s)" % ",".join(map(str, ids)))
```

### Safe

```python
cursor.execute(
    "SELECT * FROM users WHERE email = %s",
    (email,),
)
cursor.execute(
    "SELECT * FROM users WHERE id = ANY(%s)",
    (ids,),
)
```

`psycopg2` uses `%s` as its placeholder. It is NOT string
formatting; the driver handles quoting. Never use `%` on the
query string itself.

For dynamic identifiers (table or column names), use
`psycopg2.sql`:

```python
from psycopg2 import sql
query = sql.SQL("SELECT * FROM {table} WHERE id = %s").format(
    table=sql.Identifier(table_name),
)
cursor.execute(query, (user_id,))
```

Validate `table_name` against an allowlist before the SQL builder
call.

## asyncpg

### Vulnerable

```python
await conn.fetch(f"SELECT * FROM users WHERE id = {user_id}")
```

### Safe

```python
await conn.fetch(
    "SELECT * FROM users WHERE id = $1",
    user_id,
)
```

`asyncpg` uses `$1`, `$2`, ... positional placeholders.

## SQLAlchemy Core (`text()`)

### Vulnerable

```python
from sqlalchemy import text
result = conn.execute(
    text(f"SELECT * FROM users WHERE name = '{name}'"),
)
```

### Safe

```python
result = conn.execute(
    text("SELECT * FROM users WHERE name = :name"),
    {"name": name},
)
```

## SQLAlchemy ORM

### Vulnerable

```python
User.__table__.raw(f"SELECT * FROM users WHERE id = {user_id}")
session.execute(f"SELECT * FROM users WHERE id = {user_id}")
```

### Safe

```python
session.query(User).filter_by(id=user_id).first()
session.execute(
    text("SELECT * FROM users WHERE id = :id"),
    {"id": user_id},
)
```

The ORM's `filter_by`, `filter`, and `where` methods parameterize
automatically.

## Django ORM

### Vulnerable

```python
User.objects.raw(f"SELECT * FROM users WHERE id = {user_id}")
User.objects.raw("SELECT * FROM users WHERE id = %s" % user_id)
User.objects.extra(where=[f"id = {user_id}"])
```

### Safe

```python
User.objects.get(id=user_id)
User.objects.raw(
    "SELECT * FROM users WHERE id = %s",
    [user_id],
)
User.objects.extra(where=["id = %s"], params=[user_id])
```

Django's `.get`, `.filter`, `.exclude` parameterize by default. The
`raw` and `extra` methods accept parameter lists.

## pandas.read_sql

### Vulnerable

```python
df = pd.read_sql(
    f"SELECT * FROM users WHERE created > '{cutoff}'",
    conn,
)
```

### Safe

```python
df = pd.read_sql(
    "SELECT * FROM users WHERE created > %s",
    conn,
    params=(cutoff,),
)
```

## Dynamic table or column names

Parameter placeholders do NOT cover identifiers. For dynamic table
or column names, validate against an allowlist:

```python
ALLOWED_SORT_COLUMNS = {"created_at", "updated_at", "name"}
if sort_col not in ALLOWED_SORT_COLUMNS:
    raise ValueError(f"Invalid sort column: {sort_col}")
cursor.execute(
    f"SELECT * FROM users ORDER BY {sort_col} LIMIT ?",
    (limit,),
)
```

The allowlist check is the safety measure. The f-string is safe
only because `sort_col` is guaranteed to be one of a fixed set.
