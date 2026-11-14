# JavaScript SQL injection patterns

Vulnerable-vs-safe snippets for Node.js DB drivers the
`injection.sql` scanner recognizes. TypeScript-specific patterns
live in `typescript.md`.

## node-postgres (`pg`)

### Vulnerable

```javascript
const userId = req.params.id;
const rows = await client.query(
  "SELECT * FROM users WHERE id = " + userId,
);
const rows = await client.query(
  `SELECT * FROM users WHERE email = '${email}'`,
);
```

### Safe

```javascript
const rows = await client.query(
  "SELECT * FROM users WHERE id = $1",
  [userId],
);

const rows = await client.query(
  "SELECT * FROM users WHERE email = $1 AND active = $2",
  [email, true],
);
```

`pg` uses `$1`, `$2`, ... positional placeholders and a bind array
as the second argument.

## mysql / mysql2

### Vulnerable

```javascript
const rows = await conn.query(
  "SELECT * FROM users WHERE id = " + userId,
);
const rows = await conn.query(
  `SELECT * FROM users WHERE name = '${name}'`,
);
```

### Safe

```javascript
const [rows] = await conn.query(
  "SELECT * FROM users WHERE id = ?",
  [userId],
);

const [rows] = await conn.execute(
  "SELECT * FROM users WHERE name = ? AND role = ?",
  [name, role],
);
```

`mysql2` uses `?` positional placeholders. `.execute()` uses
server-side prepared statements; `.query()` uses client-side
escaping. Both are safe when the value goes through the bind array.

## Knex

### Vulnerable

```javascript
const rows = await knex.raw(
  `SELECT * FROM users WHERE id = ${userId}`,
);
const rows = await knex("users").whereRaw(
  `id = ${userId}`,
);
```

### Safe

```javascript
const rows = await knex.raw(
  "SELECT * FROM users WHERE id = ?",
  [userId],
);

const rows = await knex("users").where("id", userId);
const rows = await knex("users").whereRaw(
  "id = ?",
  [userId],
);
```

Knex's builder methods (`where`, `whereIn`, `join`) parameterize by
default. When `.raw()` or `.whereRaw()` is truly needed, pass
bindings as the second argument.

## Sequelize

### Vulnerable

```javascript
const rows = await sequelize.query(
  `SELECT * FROM users WHERE id = ${userId}`,
);
```

### Safe

```javascript
const rows = await sequelize.query(
  "SELECT * FROM users WHERE id = :id",
  {
    replacements: { id: userId },
    type: sequelize.QueryTypes.SELECT,
  },
);

const rows = await sequelize.query(
  "SELECT * FROM users WHERE id = ?",
  {
    bind: [userId],
    type: sequelize.QueryTypes.SELECT,
  },
);
```

`replacements` are escaped by Sequelize; `bind` uses the driver's
bind protocol. Never interpolate directly into the SQL string.

## Better-sqlite3

### Vulnerable

```javascript
const rows = db.prepare(
  `SELECT * FROM users WHERE id = ${userId}`,
).all();
```

### Safe

```javascript
const stmt = db.prepare(
  "SELECT * FROM users WHERE id = ?",
);
const rows = stmt.all(userId);

const stmt = db.prepare(
  "SELECT * FROM users WHERE id = @id",
);
const rows = stmt.all({ id: userId });
```

## Dynamic table or column names

Placeholders cover values only. For dynamic identifiers, validate
against an allowlist:

```javascript
const ALLOWED_SORT = new Set(["name", "created_at", "updated_at"]);
if (!ALLOWED_SORT.has(sortCol)) {
  throw new Error(`Invalid sort column: ${sortCol}`);
}
const rows = await client.query(
  `SELECT * FROM users ORDER BY ${sortCol} LIMIT $1`,
  [limit],
);
```

The allowlist is the safety measure. The template literal is safe
only because `sortCol` is guaranteed to be a known column.
