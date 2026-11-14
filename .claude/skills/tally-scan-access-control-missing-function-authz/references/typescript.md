# TypeScript missing function-level authorization patterns

Vulnerable-vs-safe snippets for the TypeScript frameworks the
`access_control.missing_function_authz` scanner recognizes. When
multiple safe forms exist, the canonical one is shown first.

## NestJS

### Vulnerable

```typescript
import { Controller, Post, Put, Body, Param } from '@nestjs/common';

@Controller('users')
export class UserController {
    // POST handler without @UseGuards or auth check
    @Post()
    async create(@Body() data: CreateUserDto) {
        // Any request can create users
        return this.userService.create(data);
    }

    // PUT handler without authorization decorator
    @Put(':id')
    async update(
        @Param('id') id: string,
        @Body() data: UpdateUserDto,
    ) {
        // State-changing without auth
        return this.userService.update(id, data);
    }
}

// Controller method without @UseGuards on admin action
@Post('grant-admin')
async grantAdmin(@Body() data: GrantAdminDto) {
    // Unprotected privilege escalation endpoint
    return this.userService.grantAdmin(data.user_id);
}
```

### Safe

```typescript
import { Controller, Post, Put, Body, Param, UseGuards } from
    '@nestjs/common';
import { AuthGuard } from '@nestjs/passport';
import { RolesGuard } from './roles.guard';
import { Roles } from './roles.decorator';

@Controller('users')
@UseGuards(AuthGuard('jwt'))
export class UserController {
    // All routes on this controller require JWT auth
    @Post()
    async create(@Body() data: CreateUserDto) {
        return this.userService.create(data);
    }

    // PUT handler with auth guard from class-level decorator
    @Put(':id')
    async update(
        @Param('id') id: string,
        @Body() data: UpdateUserDto,
    ) {
        return this.userService.update(id, data);
    }

    // Admin-only action with role check
    @Post('grant-admin')
    @UseGuards(RolesGuard)
    @Roles('admin')
    async grantAdmin(@Body() data: GrantAdminDto) {
        return this.userService.grantAdmin(data.user_id);
    }
}
```

Define a custom RolesGuard:

```typescript
import { Injectable } from '@nestjs/common';
import {
    CanActivate,
    ExecutionContext,
} from '@nestjs/common';
import { Reflector } from '@nestjs/core';

@Injectable()
export class RolesGuard implements CanActivate {
    constructor(private reflector: Reflector) {}

    canActivate(context: ExecutionContext): boolean {
        const roles = this.reflector.get<string[]>(
            'roles',
            context.getHandler(),
        );
        if (!roles) {
            return true;
        }

        const request = context.switchToHttp().getRequest();
        const user = request.user;
        return roles.some((role) => user.roles?.includes(role));
    }
}
```

## Fastify with TypeScript

### Vulnerable

```typescript
import Fastify, { FastifyRequest, FastifyReply } from 'fastify';

const fastify = Fastify();

// POST route with no auth preHandler hook
fastify.post<{ Body: CreateUserDto }>(
    '/users',
    async (request: FastifyRequest, reply: FastifyReply) => {
        // Any request can create users
        const user = await User.create(request.body);
        reply.send({ id: user.id });
    },
);

// PUT route without security
fastify.put<{
    Params: { id: string };
    Body: UpdateUserDto;
}>('/users/:id', async (request, reply) => {
    // State-changing without auth
    const user = await User.findByIdAndUpdate(
        request.params.id,
        request.body,
    );
    reply.send({ status: 'ok' });
});
```

### Safe

```typescript
import Fastify, {
    FastifyRequest,
    FastifyReply,
} from 'fastify';

const fastify = Fastify();

// Auth preHandler hook
const authHook = async (
    request: FastifyRequest,
    reply: FastifyReply,
) => {
    try {
        const token = request.headers.authorization?.split(' ')[1];
        const user = verifyToken(token);
        request.user = user;
    } catch (err) {
        reply.status(403).send({ error: 'Unauthorized' });
    }
};

// Role-check preHandler hook
const adminHook = async (
    request: FastifyRequest,
    reply: FastifyReply,
) => {
    await authHook(request, reply);
    if (request.user.role !== 'admin') {
        reply.status(403).send({ error: 'Forbidden' });
    }
};

// POST route with auth hook
fastify.post<{ Body: CreateUserDto }>(
    '/users',
    { preHandler: [authHook] },
    async (request: FastifyRequest, reply: FastifyReply) => {
        const user = await User.create(request.body);
        reply.send({ id: user.id });
    },
);

// PUT route with auth hook
fastify.put<{
    Params: { id: string };
    Body: UpdateUserDto;
}>(
    '/users/:id',
    { preHandler: [authHook] },
    async (request, reply) => {
        const user = await User.findByIdAndUpdate(
            request.params.id,
            request.body,
        );
        reply.send({ status: 'ok' });
    },
);

// Admin route with role check hook
fastify.post<{ Body: GrantAdminDto }>(
    '/admin/grant-role',
    { preHandler: [adminHook] },
    async (request: FastifyRequest, reply: FastifyReply) => {
        const updated = await User.findByIdAndUpdate(
            request.body.user_id,
            { role: 'admin' },
        );
        reply.send({ status: 'ok' });
    },
);
```

## Express with TypeScript

### Vulnerable

```typescript
import express, {
    Express,
    Request,
    Response,
} from 'express';

const app: Express = express();

// POST endpoint with no auth middleware
app.post('/users', (req: Request, res: Response) => {
    // Any user can create users
    const user = User.create({ email: req.body.email });
    res.json({ id: user.id });
});

// State-changing endpoint without auth
app.put('/users/:id', (req: Request, res: Response) => {
    const user = User.findById(req.params.id);
    user.is_admin = req.body.is_admin;
    user.save();
    res.json({ status: 'ok' });
});
```

### Safe

```typescript
import express, {
    Express,
    Request,
    Response,
    NextFunction,
} from 'express';

const app: Express = express();

// Auth middleware
const authMiddleware = (
    req: Request,
    res: Response,
    next: NextFunction,
) => {
    const token = req.headers.authorization?.split(' ')[1];
    try {
        const user = verifyToken(token);
        req.user = user;
        next();
    } catch (err) {
        res.status(403).json({ error: 'Unauthorized' });
    }
};

// POST endpoint with auth middleware
app.post(
    '/users',
    authMiddleware,
    (req: Request, res: Response) => {
        const user = User.create({ email: req.body.email });
        res.json({ id: user.id });
    },
);

// PUT endpoint with auth middleware
app.put(
    '/users/:id',
    authMiddleware,
    (req: Request, res: Response) => {
        const user = User.findById(req.params.id);
        user.is_admin = req.body.is_admin;
        user.save();
        res.json({ status: 'ok' });
    },
);

// Admin router with role check
const adminRouter = express.Router();
adminRouter.use(authMiddleware);
adminRouter.use((req: Request, res: Response, next: NextFunction) => {
    if (req.user.role !== 'admin') {
        return res.status(403).json({ error: 'Forbidden' });
    }
    next();
});

adminRouter.post(
    '/grant-admin',
    (req: Request, res: Response) => {
        const user = User.findById(req.body.user_id);
        user.role = 'admin';
        user.save();
        res.json({ status: 'ok' });
    },
);

app.use('/admin', adminRouter);
```
