# Python NoSQL injection patterns

Vulnerable-vs-safe snippets for the Python NoSQL drivers and ORMs the
`injection.nosql` scanner recognizes. When multiple safe forms exist, the
canonical one is shown first.

## pymongo

### Operator injection (vulnerable)

```python
user_id = request.get_json()
collection.find({"user": user_id})
```

If `user_id` is parsed as `{"$gt": ""}`, the query becomes `{"user": 
{"$gt": ""}}`, changing semantics to "user greater than empty string"
(matches all).

```python
body = request.get_json()
collection.insert_one(body)
```

Attacker sends `{"$set": {"role": "admin"}}` and modifies the inserted
document or triggers an operator on insert.

### Operator injection (safe)

```python
user_id = request.get_json()
collection.find({"user": str(user_id)})
```

Converting to a scalar string prevents operator injection.

```python
body = request.get_json()
collection.insert_one({
    "username": str(body.get("username")),
    "email": str(body.get("email")),
})
```

Extract and explicitly type fields from request data.

### $where injection (vulnerable)

```python
user_input = request.args.get("name")
collection.find({"$where": f"this.name == '{user_input}'"})
```

User input reaches JavaScript evaluation. Attacker can inject `'; return 
true; //` to bypass the condition.

### $where injection (safe)

```python
collection.find({"name": user_input})
```

Use query operators instead of `$where`. Never evaluate user input as
JavaScript code.

## motor (async pymongo)

### Vulnerable

```python
body = request.get_json()
await collection.insert_one(body)
```

Same operator injection risk as pymongo; `motor` is pymongo's async
wrapper with identical semantics.

### Safe

```python
body = request.get_json()
await collection.insert_one({
    "status": str(body.get("status", "pending")),
    "user_id": int(body.get("user_id", 0)),
})
```

Validate and cast fields before insertion.

## Preventing operator injection: mongo-sanitize

For Python, the `python-bson` or third-party sanitization libraries can
strip dangerous keys:

```python
def sanitize_obj(obj):
    if isinstance(obj, dict):
        return {k: sanitize_obj(v) for k, v in obj.items()
                if not k.startswith('$')}
    if isinstance(obj, list):
        return [sanitize_obj(i) for i in obj]
    return obj

body = request.get_json()
collection.insert_one(sanitize_obj(body))
```

Or use a schema validation library like `pydantic` to enforce field
constraints:

```python
from pydantic import BaseModel

class UserInsert(BaseModel):
    username: str
    email: str

body = request.get_json()
user_data = UserInsert(**body)
collection.insert_one(user_data.dict())
```

## Dynamic field access from queries

If you must build queries dynamically, allowlist the field names:

```python
ALLOWED_FIELDS = {"username", "email", "status"}
field = request.args.get("filter_field")
if field not in ALLOWED_FIELDS:
    raise ValueError("Invalid filter field")
value = request.args.get("filter_value")
collection.find({field: value})
```

The allowlist ensures `field` cannot inject operators, and `value` is
treated as a scalar.
