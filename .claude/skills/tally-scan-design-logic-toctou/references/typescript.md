# TypeScript TOCTOU race condition patterns

Vulnerable-vs-safe snippets for TypeScript database and file operations
the `design_logic.toctou` scanner recognizes. TypeScript is a superset of
JavaScript; the fs module patterns from `javascript.md` apply. These
examples focus on typed ORM and async patterns.

## Prisma findFirst then create (without upsert)

### Vulnerable

```typescript
async function getOrCreateUser(email: string): Promise<User> {
    const existing = await prisma.user.findFirst({
        where: { email }
    });
    if (!existing) {
        return await prisma.user.create({
            data: { email }
        });
    }
    return existing;
}
```

### Safe

```typescript
async function getOrCreateUser(email: string): Promise<User> {
    return await prisma.user.upsert({
        where: { email },
        update: {},
        create: { email }
    });
}

async function multiStepTransfer(
    from_id: number,
    to_id: number,
    amount: number
): Promise<void> {
    await prisma.$transaction(async (tx) => {
        const from = await tx.account.update({
            where: { id: from_id },
            data: { balance: { decrement: amount } }
        });
        if (from.balance < 0) {
            throw new Error("Insufficient balance");
        }
        await tx.account.update({
            where: { id: to_id },
            data: { balance: { increment: amount } }
        });
    });
}
```

`upsert()` is atomic. Prisma uses an atomic database operation (INSERT ...
ON CONFLICT) under the hood. For multi-step operations, wrap them in
`prisma.$transaction()` to ensure all-or-nothing semantics.

## TypeORM repository find then save

### Vulnerable

```typescript
async function getOrCreateUser(email: string): Promise<User> {
    const repo = getRepository(User);
    let user = await repo.findOneBy({ email });
    if (!user) {
        user = new User();
        user.email = email;
        await repo.save(user);
    }
    return user;
}

async function debitBalance(
    userId: number,
    amount: number
): Promise<void> {
    const repo = getRepository(Account);
    const account = await repo.findOneBy({ id: userId });
    if (account.balance >= amount) {
        account.balance -= amount;
        await repo.save(account);
    }
}
```

### Safe

```typescript
async function getOrCreateUser(email: string): Promise<User> {
    const repo = getRepository(User);
    return await repo.upsert(
        { email },
        { skipUpdateIfNoChange: true }
    );
}

async function debitBalance(
    userId: number,
    amount: number
): Promise<void> {
    const qr = dataSource.createQueryRunner();
    await qr.connect();
    await qr.startTransaction();
    try {
        const account = await qr.manager.findOneBy(Account, {
            id: userId
        });
        if (!account || account.balance < amount) {
            throw new Error("Insufficient balance");
        }
        account.balance -= amount;
        await qr.manager.save(account);
        await qr.commitTransaction();
    } catch (err) {
        await qr.rollbackTransaction();
        throw err;
    } finally {
        await qr.release();
    }
}

@Transaction()
async function debitWithDecorator(
    userId: number,
    amount: number
): Promise<void> {
    const repo = getRepository(Account);
    const account = await repo.findOneBy({ id: userId });
    if (!account || account.balance < amount) {
        throw new Error("Insufficient balance");
    }
    account.balance -= amount;
    await repo.save(account);
}
```

TypeORM's `upsert()` is atomic. For custom transactions, use a
`QueryRunner` to acquire an explicit transaction boundary. Alternatively,
use the `@Transaction()` decorator to wrap the entire method.

## Sequelize findOrCreate (typed)

### Vulnerable

```typescript
import { User } from './models/User';

async function getOrCreateUser(email: string): Promise<User> {
    const user = await User.findOne({ where: { email } });
    if (!user) {
        return await User.create({ email });
    }
    return user;
}
```

### Safe

```typescript
import { User } from './models/User';

async function getOrCreateUser(email: string): Promise<User> {
    const [user, created] = await User.findOrCreate({
        where: { email },
        defaults: { email }
    });
    return user;
}
```

Sequelize's `findOrCreate()` is atomic, even when used with TypeScript
models. It uses INSERT ... ON DUPLICATE KEY UPDATE or equivalent.

## fs.promises with TypeScript (proper type narrowing)

### Vulnerable

```typescript
import * as fs from 'fs/promises';
import * as fsSync from 'fs';

async function readConfig(path: string): Promise<string> {
    if (fsSync.existsSync(path)) {
        return await fs.readFile(path, 'utf-8');
    }
    return '';
}
```

### Safe

```typescript
import * as fs from 'fs/promises';

async function readConfig(path: string): Promise<string> {
    try {
        return await fs.readFile(path, 'utf-8');
    } catch (err: unknown) {
        if (err instanceof Error && err.message.includes('ENOENT')) {
            return '';
        }
        throw err;
    }
}

async function createExclusiveFile(
    path: string,
    data: string
): Promise<void> {
    try {
        const fd = await fs.open(path, 'wx');
        await fd.write(data);
        await fd.close();
    } catch (err: unknown) {
        if (err instanceof Error && err.message.includes('EEXIST')) {
            throw new Error('File already exists');
        }
        throw err;
    }
}
```

Use `fs.promises.open(path, 'wx')` for atomic exclusive creation. For
reads, call `fs.readFile` directly and handle `ENOENT` in the catch block.
Avoid mixing sync and async fs calls; async operations have a larger race
window.

## Database transaction with typed query builder

### Vulnerable

```typescript
interface Reservation {
    id: number;
    slot_id: number;
    user_id: number;
}

async function reserveSlot(
    slot_id: number,
    user_id: number
): Promise<boolean> {
    const reserved = await db.query(
        'SELECT id FROM reservations WHERE slot_id = ?',
        [slot_id]
    );
    if (reserved.length === 0) {
        await db.query(
            'INSERT INTO reservations (slot_id, user_id) VALUES (?, ?)',
            [slot_id, user_id]
        );
        return true;
    }
    return false;
}
```

### Safe

```typescript
interface Reservation {
    id: number;
    slot_id: number;
    user_id: number;
}

async function reserveSlot(
    slot_id: number,
    user_id: number
): Promise<boolean> {
    const qr = dataSource.createQueryRunner();
    await qr.connect();
    await qr.startTransaction();
    try {
        const reserved = await qr.query(
            'SELECT id FROM reservations WHERE slot_id = ? FOR UPDATE',
            [slot_id]
        );
        if (reserved.length === 0) {
            await qr.query(
                'INSERT INTO reservations (slot_id, user_id) VALUES (?, ?)',
                [slot_id, user_id]
            );
            await qr.commitTransaction();
            return true;
        }
        await qr.rollbackTransaction();
        return false;
    } catch (err) {
        await qr.rollbackTransaction();
        throw err;
    } finally {
        await qr.release();
    }
}
```

Wrap the check-and-insert in a database transaction with `SELECT ... FOR
UPDATE` to lock the rows. This prevents another connection from inserting
during the transaction.
