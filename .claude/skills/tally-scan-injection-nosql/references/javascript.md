# JavaScript NoSQL injection patterns

Vulnerable-vs-safe snippets for the Node.js NoSQL libraries the
`injection.nosql` scanner recognizes. When multiple safe forms exist, the
canonical one is shown first.

## mongodb (native driver)

### Operator injection (vulnerable)

```javascript
const body = req.body;
const result = await collection.find({user: body.user}).toArray();
```

If `body.user` is `{"$gt": ""}`, the query becomes `{user: {"$gt": 
""}}`, matching all documents.

```javascript
const body = req.body;
await collection.insertOne(body);
```

Attacker sends `{"$set": {"role": "admin"}}` and injects operators into
the inserted document.

### Operator injection (safe)

```javascript
const userId = String(req.body.user_id);
const result = await collection.find({user_id: userId}).toArray();
```

Coerce user input to a scalar string before using as a query value.

```javascript
const body = req.body;
await collection.insertOne({
    username: String(body.username),
    email: String(body.email),
    created_at: new Date(),
});
```

Extract and explicitly cast fields from request data.

### Operator injection with Object.assign (vulnerable)

```javascript
const filters = {status: 'active'};
const userFilters = req.query;
const query = Object.assign({}, filters, userFilters);
const result = await collection.find(query).toArray();
```

User-supplied keys can inject operators like `$where` or `$regex`.

### Operator injection with Object.assign (safe)

```javascript
const filters = {status: 'active'};
const ALLOWED_FIELDS = ['username', 'email', 'created_after'];
const userFilters = req.query;
const safe = {};
for (const key of ALLOWED_FIELDS) {
    if (key in userFilters) {
        safe[key] = String(userFilters[key]);
    }
}
const query = Object.assign({}, filters, safe);
const result = await collection.find(query).toArray();
```

Whitelist allowed fields before merging user input.

### $where injection (vulnerable)

```javascript
const name = req.query.name;
const result = await collection.find({$where: `this.name == '${name}'`}).toArray();
```

User input reaches JavaScript evaluation. Attacker can inject `'; return 
true; //`.

### $where injection (safe)

```javascript
const name = req.query.name;
const result = await collection.find({name: name}).toArray();
```

Use query operators instead of `$where`. Never evaluate user input as
JavaScript code.

## mongoose

### Operator injection (vulnerable)

```javascript
const body = req.body;
const user = await User.find(body).exec();
```

If `body` contains operator keys, they affect the query.

### Operator injection (safe)

```javascript
const body = req.body;
const user = await User.find({
    username: String(body.username),
    email: String(body.email),
}).exec();
```

Build queries from explicitly named fields with scalar values.

### Mongoose schema validation (safe)

```javascript
const userSchema = new mongoose.Schema({
    username: { type: String, required: true },
    email: { type: String, required: true },
});
const User = mongoose.model('User', userSchema);

const body = req.body;
const user = new User(body);
await user.save();
```

Schema validation enforces field names and types, preventing operator
injection during model instantiation.

### Dynamic filter with allowlist (safe)

```javascript
const body = req.body;
const ALLOWED_FIELDS = ['username', 'status', 'email'];
const filter = {};
for (const field of ALLOWED_FIELDS) {
    if (field in body) {
        filter[field] = String(body[field]);
    }
}
const user = await User.findOne(filter).exec();
```

Whitelist fields and coerce values to scalars.

## Preventing operator injection: mongo-sanitize

Apply a sanitization library to strip keys starting with `$` or `.`:

```javascript
const mongoSanitize = require('mongo-sanitize');

const body = req.body;
const sanitized = mongoSanitize(body);
await collection.insertOne(sanitized);
```

Or implement sanitization inline:

```javascript
function sanitizeOperators(obj) {
    if (typeof obj !== 'object' || obj === null) {
        return obj;
    }
    const result = Array.isArray(obj) ? [] : {};
    for (const key in obj) {
        if (!key.startsWith('$') && !key.startsWith('.')) {
            result[key] = sanitizeOperators(obj[key]);
        }
    }
    return result;
}

const body = req.body;
const sanitized = sanitizeOperators(body);
await collection.insertOne(sanitized);
```
