# TypeScript race condition patterns

Vulnerable-vs-safe snippets for the TypeScript concurrent operations the
`design_logic.race_condition` scanner recognizes.

## Prisma concurrent modifications without transaction

### Vulnerable

```typescript
import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

async function transfer_credits(userId: string, amount: number) {
    const user = await prisma.user.findUnique({ where: { id: userId } });
    
    if (user && user.credits >= amount) {
        await prisma.user.update({
            where: { id: userId },
            data: { credits: { decrement: amount } }
        });
        return true;
    }
    return false;
}
```

### Safe

```typescript
import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

async function transfer_credits(userId: string, amount: number) {
    const result = await prisma.$transaction(async (tx) => {
        const user = await tx.user.findUnique({ where: { id: userId } });
        
        if (user && user.credits >= amount) {
            await tx.user.update({
                where: { id: userId },
                data: { credits: { decrement: amount } }
            });
            return true;
        }
        return false;
    });
    
    return result;
}
```

Wrap the read and update in `prisma.$transaction()` to ensure all operations
are atomic. The transaction automatically rolls back if an error occurs.

## TypeORM concurrent modifications without transaction

### Vulnerable

```typescript
import { getRepository } from 'typeorm';
import { User } from './User';

async function transfer_credits(userId: string, amount: number) {
    const userRepo = getRepository(User);
    const user = await userRepo.findOne(userId);
    
    if (user && user.credits >= amount) {
        user.credits -= amount;
        await userRepo.save(user);
        return true;
    }
    return false;
}
```

### Safe (Option 1: @Transaction decorator)

```typescript
import { getRepository } from 'typeorm';
import { Transaction } from 'typeorm';
import { User } from './User';

@Transaction()
async function transfer_credits(
    userId: string,
    amount: number,
    @TransactionManager() manager?: EntityManager
) {
    const user = await manager.findOne(User, userId);
    
    if (user && user.credits >= amount) {
        user.credits -= amount;
        await manager.save(user);
        return true;
    }
    return false;
}
```

### Safe (Option 2: QueryRunner)

```typescript
import { getConnection } from 'typeorm';
import { User } from './User';

async function transfer_credits(userId: string, amount: number) {
    const connection = getConnection();
    const queryRunner = connection.createQueryRunner();
    
    await queryRunner.connect();
    await queryRunner.startTransaction();
    
    try {
        const user = await queryRunner.manager.findOne(User, userId);
        
        if (user && user.credits >= amount) {
            user.credits -= amount;
            await queryRunner.manager.save(user);
            await queryRunner.commitTransaction();
            return true;
        }
        await queryRunner.rollbackTransaction();
        return false;
    } finally {
        await queryRunner.release();
    }
}
```

Use `@Transaction()` decorator or QueryRunner to wrap the read-modify-write
sequence in a database transaction.

## Shared mutable class properties in async context

### Vulnerable

```typescript
class UserService {
    private lastUpdated: number = 0;
    
    async updateUser(userId: string, data: Partial<User>) {
        this.lastUpdated = Date.now();
        const user = await this.db.get(userId);
        
        await this.db.update(userId, data);
        
        return { user, lastUpdated: this.lastUpdated };
    }
}
```

### Safe

```typescript
class UserService {
    async updateUser(userId: string, data: Partial<User>) {
        const lastUpdated = Date.now();
        const user = await this.db.get(userId);
        
        await this.db.update(userId, data);
        
        return { user, lastUpdated };
    }
}
```

Avoid storing request-scoped or operation-scoped state in class instance
variables. Use local variables instead, or pass state through function
parameters.

## Redis atomic operation misuse in async context

### Vulnerable

```typescript
import * as redis from 'redis';

const client = redis.createClient();

async function debit_account(accountId: string, amount: number) {
    const balance = await client.get(`balance:${accountId}`);
    
    if (parseInt(balance) >= amount) {
        await client.set(
            `balance:${accountId}`,
            String(parseInt(balance) - amount)
        );
        return true;
    }
    return false;
}
```

### Safe (Option 1: Lua script)

```typescript
import * as redis from 'redis';

const client = redis.createClient();

async function debit_account(accountId: string, amount: number) {
    const script = `
        local balance = redis.call('GET', KEYS[1])
        if not balance or tonumber(balance) < tonumber(ARGV[1]) then
            return 0
        end
        redis.call('DECRBY', KEYS[1], ARGV[1])
        return 1
    `;
    
    const result = await client.eval(script, {
        keys: [`balance:${accountId}`],
        arguments: [String(amount)]
    });
    
    return result === 1;
}
```

### Safe (Option 2: SETNX for set-if-not-exists)

```typescript
import * as redis from 'redis';

const client = redis.createClient();

async function reserve_slot(slotId: string) {
    const result = await client.set(
        `slot:${slotId}`,
        'true',
        { NX: true, EX: 3600 }
    );
    return result === 'OK';
}
```

Use Lua scripts (EVAL) for complex read-check-modify operations, or SETNX
(SET with NX flag) for simple set-if-not-exists patterns.

## SharedArrayBuffer with proper Atomics

### Vulnerable

```typescript
const sharedBuffer = new SharedArrayBuffer(4);
const sharedArray = new Int32Array(sharedBuffer);

worker.postMessage({ sharedBuffer });

sharedArray[0] = 10;
const value = sharedArray[0];
```

### Safe

```typescript
const sharedBuffer = new SharedArrayBuffer(4);
const sharedArray = new Int32Array(sharedBuffer);

worker.postMessage({ sharedBuffer });

Atomics.store(sharedArray, 0, 10);
const value = Atomics.load(sharedArray, 0);

if (Atomics.compareExchange(sharedArray, 0, 10, 20) === 10) {
    // Successfully changed 10 to 20
}
```

Always use Atomics API (Atomics.load, Atomics.store, Atomics.compareExchange)
for all reads, writes, and compare-and-swap operations on SharedArrayBuffer.

## Database upsert in concurrent context

### Vulnerable

```typescript
import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

async function get_or_create_user(email: string, name: string) {
    let user = await prisma.user.findUnique({ where: { email } });
    
    if (!user) {
        user = await prisma.user.create({
            data: { email, name }
        });
    }
    
    return user;
}
```

### Safe

```typescript
import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

async function get_or_create_user(email: string, name: string) {
    const user = await prisma.user.upsert({
        where: { email },
        update: { name },
        create: { email, name }
    });
    
    return user;
}
```

Use `upsert()` to make the find-or-create operation atomic. The database
engine handles the race condition between the find and create.
