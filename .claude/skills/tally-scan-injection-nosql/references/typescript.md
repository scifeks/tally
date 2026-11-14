# TypeScript NoSQL injection patterns

Vulnerable-vs-safe snippets for the TypeScript NoSQL libraries the
`injection.nosql` scanner recognizes. When multiple safe forms exist, the
canonical one is shown first.

## mongodb (native driver)

### Operator injection (vulnerable)

```typescript
const body = req.body as any;
const result = await collection.find({user: body.user}).toArray();
```

If `body.user` is `{$gt: ""}`, the query becomes `{user: {$gt: ""}}`,
matching all documents. The `as any` cast bypasses TypeScript's safety.

### Operator injection (safe)

```typescript
const userId: string = String(req.body.user_id);
const result = await collection.find({user_id: userId}).toArray();
```

Explicitly type-cast user input to a scalar before using as a query value.

```typescript
interface UserInsert {
    username: string;
    email: string;
}

const body = req.body as UserInsert;
await collection.insertOne({
    username: body.username,
    email: body.email,
    created_at: new Date(),
});
```

Use an interface to enforce field structure and types.

## mongoose (with TypeScript)

### Operator injection (vulnerable)

```typescript
const body = req.body as any;
const user = await User.find(body).exec();
```

Bypassing Mongoose's type system allows arbitrary operator keys.

### Operator injection (safe)

```typescript
const body = req.body;
const user = await User.find({
    username: String(body.username),
    email: String(body.email),
}).exec();
```

Build queries from explicitly named fields with scalar values.

### Typed model instantiation (safe)

```typescript
interface IUser {
    username: string;
    email: string;
    status?: string;
}

const userSchema = new mongoose.Schema<IUser>({
    username: { type: String, required: true },
    email: { type: String, required: true },
    status: { type: String, default: 'pending' },
});

const User = mongoose.model<IUser>('User', userSchema);

const body = req.body as IUser;
const user = new User(body);
await user.save();
```

TypeScript generics and schema definitions enforce field names and types,
preventing operator injection during model instantiation.

### Dynamic filter with type guards (safe)

```typescript
const body = req.body;
const ALLOWED_FIELDS: (keyof IUser)[] = ['username', 'email', 'status'];

const filter: Partial<IUser> = {};
for (const field of ALLOWED_FIELDS) {
    if (field in body) {
        filter[field] = String(body[field]) as any;
    }
}

const user = await User.findOne(filter).exec();
```

Use TypeScript's `Partial` type and field allowlist to enforce safe query
construction.

### Query helper method (safe)

```typescript
class UserRepository {
    async findByUsernameAndEmail(
        username: string,
        email: string
    ): Promise<IUser | null> {
        return User.findOne({
            username: username,
            email: email,
        }).exec();
    }
}

const repo = new UserRepository();
const body = req.body;
const user = await repo.findByUsernameAndEmail(
    String(body.username),
    String(body.email)
);
```

Encapsulate query building in typed repository methods that accept scalar
parameters.

## Preventing operator injection: mongo-sanitize

Apply a sanitization library before passing to Mongoose or MongoDB:

```typescript
import mongoSanitize from 'mongo-sanitize';

const body = req.body;
const sanitized = mongoSanitize(body);
const user = new User(sanitized);
await user.save();
```

Or implement sanitization with TypeScript:

```typescript
function sanitizeOperators<T extends Record<string, any>>(
    obj: T
): T {
    if (typeof obj !== 'object' || obj === null) {
        return obj;
    }
    const result = (Array.isArray(obj) ? [] : {}) as T;
    for (const key in obj) {
        if (!key.startsWith('$') && !key.startsWith('.')) {
            result[key] = sanitizeOperators(obj[key]);
        }
    }
    return result;
}

const body = req.body;
const sanitized = sanitizeOperators(body);
const user = new User(sanitized);
await user.save();
```

## TypeScript-specific considerations

TypeScript's type system does not prevent operator injection at runtime.
The type checker enforces type contracts at compile time, but using `as 
any` or casting request data to a model interface bypasses this safety.

Always:

1. Extract and explicitly cast scalar fields from request data.
2. Use repository or query-building methods that accept typed parameters.
3. Avoid casting request objects directly to model interfaces with `as`.
4. Apply mongo-sanitize or equivalent if you must pass user-controlled
   objects directly to query methods.
