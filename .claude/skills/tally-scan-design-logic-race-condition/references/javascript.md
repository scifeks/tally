# JavaScript race condition patterns

Vulnerable-vs-safe snippets for the Node.js concurrent operations the
`design_logic.race_condition` scanner recognizes.

## Promise.all with shared mutable state

### Vulnerable

```javascript
const results = { count: 0, total: 0 };

async function process_items(items) {
    await Promise.all(items.map(async (item) => {
        results.count += 1;
        const value = await fetch_value(item);
        results.total += value;
    }));
    return results;
}
```

### Safe

```javascript
async function process_items(items) {
    const promises = items.map(async (item) => {
        const value = await fetch_value(item);
        return { count: 1, total: value };
    });
    
    const all_results = await Promise.all(promises);
    const results = all_results.reduce(
        (acc, r) => ({
            count: acc.count + r.count,
            total: acc.total + r.total
        }),
        { count: 0, total: 0 }
    );
    return results;
}
```

Avoid modifying shared objects from concurrent promises. Instead, have each
promise return its result and aggregate the results after all promises
resolve.

## Worker thread data races on SharedArrayBuffer

### Vulnerable

```javascript
const sharedBuffer = new SharedArrayBuffer(4);
const sharedArray = new Int32Array(sharedBuffer);

const worker = new Worker('worker.js');
worker.postMessage({ sharedBuffer });

sharedArray[0] = 10;
const result = sharedArray[0];
```

### Safe

```javascript
const sharedBuffer = new SharedArrayBuffer(4);
const sharedArray = new Int32Array(sharedBuffer);

const worker = new Worker('worker.js');
worker.postMessage({ sharedBuffer });

Atomics.store(sharedArray, 0, 10);
const result = Atomics.load(sharedArray, 0);
```

Use the Atomics API (Atomics.load, Atomics.store, Atomics.compareExchange)
for all reads and writes to SharedArrayBuffer to ensure atomicity.

## Event loop state mutation across async callbacks

### Vulnerable

```javascript
let global_user_id = null;

app.post('/transfer', async (req, res) => {
    global_user_id = req.body.from_user_id;
    
    const balance = await db.get_balance(global_user_id);
    if (balance >= req.body.amount) {
        await db.debit(global_user_id, req.body.amount);
        res.json({ status: 'ok' });
    }
});
```

### Safe

```javascript
app.post('/transfer', async (req, res) => {
    const user_id = req.body.from_user_id;
    
    const balance = await db.get_balance(user_id);
    if (balance >= req.body.amount) {
        await db.debit(user_id, req.body.amount);
        res.json({ status: 'ok' });
    }
});
```

Avoid global variables in async request handlers. Use local variables or
request-scoped context (Express locals, middleware storage) to avoid races
between concurrent requests.

## Redis check-then-act without atomicity

### Vulnerable

```javascript
const redis = require('redis').createClient();

async function reserve_slot(slot_id) {
    const reserved = await redis.get(`slot:${slot_id}`);
    if (!reserved) {
        await redis.set(`slot:${slot_id}`, 'true');
        return true;
    }
    return false;
}
```

### Safe (Option 1: SETNX)

```javascript
const redis = require('redis').createClient();

async function reserve_slot(slot_id) {
    const result = await redis.set(
        `slot:${slot_id}`,
        'true',
        { NX: true }
    );
    return result === 'OK';
}
```

### Safe (Option 2: Lua script)

```javascript
const redis = require('redis').createClient();

async function debit_balance(account_id, amount) {
    const script = `
        local balance = redis.call('GET', KEYS[1])
        if not balance or tonumber(balance) < tonumber(ARGV[1]) then
            return 0
        end
        redis.call('DECRBY', KEYS[1], ARGV[1])
        return 1
    `;
    const result = await redis.eval(
        script,
        { keys: [`balance:${account_id}`], arguments: [amount] }
    );
    return result === 1;
}
```

Use `set(..., { NX: true })` for atomic set-if-not-exists, or Lua scripts
(EVAL) for more complex read-check-modify operations.

## Concurrent map updates without synchronization

### Vulnerable

```javascript
const cache = new Map();

async function update_cache(items) {
    await Promise.all(items.map(async (item) => {
        const value = await fetch_value(item.id);
        cache.set(item.id, value);
    }));
}

async function read_cache(item_id) {
    if (cache.has(item_id)) {
        return cache.get(item_id);
    }
    return null;
}
```

### Safe

```javascript
const cache = new Map();
const lock = new Promise(resolve => resolve());

async function update_cache(items) {
    for (const item of items) {
        const value = await fetch_value(item.id);
        cache.set(item.id, value);
    }
}

async function read_cache(item_id) {
    if (cache.has(item_id)) {
        return cache.get(item_id);
    }
    return null;
}
```

For simple caches, process items sequentially instead of in parallel, or
use a third-party cache library (Redis, Memcached) with atomic operations.

## Database check-then-insert without upsert

### Vulnerable

```javascript
const mongoose = require('mongoose');

async function get_or_create_user(email, name) {
    const user = await User.findOne({ email });
    if (!user) {
        return await User.create({ email, name });
    }
    return user;
}
```

### Safe

```javascript
const mongoose = require('mongoose');

async function get_or_create_user(email, name) {
    return await User.findOneAndUpdate(
        { email },
        { email, name },
        { upsert: true, new: true }
    );
}
```

Use `findOneAndUpdate()` with `{ upsert: true }` to make the find-or-create
atomic. The database engine handles the race condition.
