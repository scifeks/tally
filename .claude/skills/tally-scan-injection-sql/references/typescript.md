# TypeScript SQL injection patterns

Vulnerable-vs-safe snippets for the TypeScript-specific ORMs the
`injection.sql` scanner recognizes. Node.js-shared patterns
(`pg`, `mysql2`, Knex, Sequelize, better-sqlite3) live in
`javascript.md`.

## Prisma

### Vulnerable

```typescript
const users = await prisma.$queryRawUnsafe(
  `SELECT * FROM users WHERE id = ${userId}`,
);

const users = await prisma.$queryRawUnsafe(
  "SELECT * FROM users WHERE email = '" + email + "'",
);
```

`$queryRawUnsafe` takes a plain string and does not parameterize.
It is a code smell in any codebase that also has `$queryRaw`
available.

### Safe

```typescript
const users = await prisma.user.findMany({
  where: { id: userId },
});

const users = await prisma.$queryRaw`
  SELECT * FROM users WHERE id = ${userId}
`;

const users = await prisma.$queryRaw(
  Prisma.sql`SELECT * FROM users WHERE id = ${userId}`,
);
```

`$queryRaw` used as a tagged template parameterizes automatically.
Prisma treats interpolations as bind parameters, not string
concatenation. The typed builder (`prisma.user.findMany`) is
safest.

Note the three shapes of `$queryRaw`:

- **Tagged template**: `prisma.$queryRaw\`SELECT ...\``. Safe.
- **Function call**: `prisma.$queryRaw(sql, ...values)`. Safe when
  the first argument is a `Prisma.sql` template literal. Unsafe
  when the first argument is a plain string.
- **`$queryRawUnsafe(string, ...values)`**. The `values` are
  bound, but the SQL string itself is not sanitized. Only safe
  when the SQL string is a compile-time constant.

## TypeORM

### Vulnerable

```typescript
const users = await connection.query(
  `SELECT * FROM users WHERE id = ${userId}`,
);

const users = await userRepository
  .createQueryBuilder("user")
  .where(`user.id = ${userId}`)
  .getMany();
```

### Safe

```typescript
const users = await connection.query(
  "SELECT * FROM users WHERE id = ?",
  [userId],
);

const users = await userRepository
  .createQueryBuilder("user")
  .where("user.id = :id", { id: userId })
  .getMany();

const users = await userRepository.findBy({ id: userId });
```

TypeORM's QueryBuilder parameterizes when the SQL fragment uses
`:name` placeholders and a params object. The typed repository
methods (`findBy`, `findOne`) parameterize by default.

## Sequelize (typed)

### Vulnerable

```typescript
const users = await sequelize.query<UserRow>(
  `SELECT * FROM users WHERE id = ${userId}`,
);

const users = await User.findAll({
  where: sequelize.literal(`id = ${userId}`),
});
```

`Sequelize.literal()` is an escape hatch that inserts the string
into the SQL verbatim. It is never safe with request data.

### Safe

```typescript
const users = await sequelize.query<UserRow>(
  "SELECT * FROM users WHERE id = :id",
  {
    replacements: { id: userId },
    type: QueryTypes.SELECT,
  },
);

const users = await User.findAll({
  where: { id: userId },
});

const users = await User.findAll({
  where: {
    [Op.and]: [{ role: "admin" }, { id: userId }],
  },
});
```

The typed `where` clause parameterizes automatically. Reach for
`literal()` only when the fragment is a compile-time constant.

## Kysely

### Vulnerable

```typescript
const users = await db
  .selectFrom("users")
  .selectAll()
  .where(sql`id = ${userId}`.raw())
  .execute();
```

`.raw()` on a `sql` template opts out of parameterization.

### Safe

```typescript
const users = await db
  .selectFrom("users")
  .selectAll()
  .where("id", "=", userId)
  .execute();

const users = await db
  .selectFrom("users")
  .selectAll()
  .where(sql`id = ${userId}`)
  .execute();
```

Kysely's `sql` template parameterizes interpolations. Never call
`.raw()` on a template that contains request data.

## Dynamic table or column names

Placeholders cover values only. For dynamic identifiers, validate
against an allowlist:

```typescript
const ALLOWED_SORT = new Set(["name", "createdAt", "updatedAt"]);
if (!ALLOWED_SORT.has(sortCol)) {
  throw new Error(`Invalid sort column: ${sortCol}`);
}
const users = await prisma.$queryRaw(
  Prisma.sql`
    SELECT * FROM users
    ORDER BY ${Prisma.raw(sortCol)}
    LIMIT ${limit}
  `,
);
```

`Prisma.raw()` opts out of parameterization for one interpolation;
the allowlist is what makes that call safe.
