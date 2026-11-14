# JavaScript TOCTOU race condition patterns

Vulnerable-vs-safe snippets for the Node.js file and database operations
the `design_logic.toctou` scanner recognizes.

## fs module (existsSync then read/write)

### Vulnerable

```javascript
const fs = require('fs');
const path = process.env.USER_FILE;

if (fs.existsSync(path)) {
    const content = fs.readFileSync(path, 'utf-8');
    console.log(content);
}

if (fs.existsSync(configPath)) {
    fs.writeFileSync(configPath, newConfig);
}
```

### Safe

```javascript
const fs = require('fs');
const path = process.env.USER_FILE;

try {
    const content = fs.readFileSync(path, 'utf-8');
    console.log(content);
} catch (err) {
    if (err.code !== 'ENOENT') {
        throw err;
    }
}

try {
    fs.writeFileSync(configPath, newConfig);
} catch (err) {
    if (err.code !== 'EACCES') {
        throw err;
    }
}
```

Eliminate the check-then-use pattern. Call `readFileSync` or `writeFileSync`
directly and handle `ENOENT` (file not found) or `EACCES` (permission denied)
errors at the point of use.

## fs.promises (async with proper error handling)

### Vulnerable

```javascript
const fs = require('fs').promises;

async function processFile() {
    const filePath = req.body.file;
    if (await fs.access(filePath, fs.constants.R_OK)) {
        const data = await fs.readFile(filePath, 'utf-8');
        return data;
    }
}

async function writeConfig() {
    if (await fileExists(configPath)) {
        await fs.writeFile(configPath, newData);
    }
}
```

### Safe

```javascript
const fs = require('fs').promises;

async function processFile() {
    const filePath = req.body.file;
    try {
        const data = await fs.readFile(filePath, 'utf-8');
        return data;
    } catch (err) {
        if (err.code === 'ENOENT') {
            return null;
        }
        throw err;
    }
}

async function writeConfig() {
    try {
        await fs.writeFile(configPath, newData);
    } catch (err) {
        if (err.code === 'EACCES') {
            throw new Error("Permission denied");
        }
        throw err;
    }
}
```

In async code, eliminate the `fs.access()` check. Call `fs.readFile` or
`fs.writeFile` directly and handle errors. The async boundary between
operations increases the race window.

## fs.open with exclusive creation flag

### Vulnerable

```javascript
const fs = require('fs');
const file = '/tmp/upload_' + userId + '.tmp';
if (!fs.existsSync(file)) {
    fs.writeFileSync(file, data);
}
```

### Safe

```javascript
const fs = require('fs');
const file = '/tmp/upload_' + userId + '.tmp';
try {
    const fd = fs.openSync(file, 'wx');
    fs.writeSync(fd, data);
    fs.closeSync(fd);
} catch (err) {
    if (err.code === 'EEXIST') {
        throw new Error("File already exists");
    }
    throw err;
}

const fsPromises = require('fs').promises;
const fd = await fsPromises.open(file, 'wx');
try {
    await fd.write(data);
} finally {
    await fd.close();
}
```

`fs.openSync(path, 'wx')` or `fs.promises.open(path, 'wx')` opens the file
in exclusive-creation mode and fails atomically with EEXIST if the file
exists. No race window.

## Mongoose findOneAndUpdate (atomic update)

### Vulnerable

```javascript
const { findOne, updateOne } = require('mongoose');

async function createOrUpdateUser(email, name) {
    const user = await User.findOne({ email });
    if (!user) {
        const newUser = new User({ email, name });
        await newUser.save();
        return newUser;
    }
    user.name = name;
    await user.save();
    return user;
}
```

### Safe

```javascript
async function createOrUpdateUser(email, name) {
    const user = await User.findOneAndUpdate(
        { email },
        { email, name },
        { upsert: true, new: true }
    );
    return user;
}
```

`findOneAndUpdate()` with `{ upsert: true }` is atomic. The database engine
checks for an existing document and inserts or updates in a single
operation. No race window between find and insert.

## Sequelize findOrCreate

### Vulnerable

```javascript
const { Sequelize } = require('sequelize');

async function getOrCreateUser(email, name) {
    const user = await User.findOne({ where: { email } });
    if (!user) {
        return await User.create({ email, name });
    }
    return user;
}
```

### Safe

```javascript
async function getOrCreateUser(email, name) {
    const [user, created] = await User.findOrCreate({
        where: { email },
        defaults: { name }
    });
    return user;
}
```

`findOrCreate()` is atomic. Sequelize uses INSERT ... ON DUPLICATE KEY
UPDATE or equivalent, eliminating the race between find and insert.

## Redis SETNX (set if not exists) for atomic operations

### Vulnerable

```javascript
const redis = require('redis');
const client = redis.createClient();

async function reserveSlot(slot_id) {
    const reserved = await client.GET(`slot:${slot_id}`);
    if (!reserved) {
        await client.SET(`slot:${slot_id}`, 'true');
        return true;
    }
    return false;
}
```

### Safe

```javascript
const redis = require('redis');
const client = redis.createClient();

async function reserveSlot(slot_id) {
    const key = `slot:${slot_id}`;
    const reserved = await client.SET(key, 'true', { NX: true });
    return reserved === 'OK';
}

async function debitBalance(account_id, amount) {
    const script = `
        local balance = redis.call('GET', KEYS[1])
        if not balance or tonumber(balance) < tonumber(ARGV[1]) then
            return 0
        end
        redis.call('DECRBY', KEYS[1], ARGV[1])
        return 1
    `;
    const result = await client.EVAL(
        script,
        1,
        `balance:${account_id}`,
        amount
    );
    return result === 1;
}
```

`client.SET(key, value, { NX: true })` (SETNX) is atomic. It sets the key
only if it does not exist, returning 'OK' on success or null on failure.
For more complex operations, use Lua scripts with `EVAL` to ensure
atomicity.
