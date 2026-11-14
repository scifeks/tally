# TypeScript insufficient logging patterns

Vulnerable-vs-safe snippets for TypeScript auth guards (NestJS),
middleware, decorators, and admin operations lacking audit trails.

## NestJS guard without logging

### Vulnerable

```typescript
@Injectable()
export class AuthGuard implements CanActivate {
    canActivate(context: ExecutionContext): boolean {
        const request = context.switchToHttp().getRequest();
        const token = request.headers.authorization?.split(' ')[1];
        if (!token) {
            throw new UnauthorizedException();
        }
        try {
            const payload = jwt.verify(token, process.env.JWT_SECRET);
            request.user = payload;
            return true;
        } catch (err) {
            throw new UnauthorizedException();
        }
    }
}

@Controller('/admin')
export class AdminController {
    @UseGuards(AuthGuard)
    @Get('/users')
    listUsers() {
        return { users: [] };
    }
}
```

### Safe

```typescript
import { Logger, Injectable } from '@nestjs/common';

@Injectable()
export class AuthGuard implements CanActivate {
    private logger = new Logger(AuthGuard.name);

    canActivate(context: ExecutionContext): boolean {
        const request = context.switchToHttp().getRequest();
        const token = request.headers.authorization?.split(' ')[1];
        if (!token) {
            this.logger.warn('Access attempt without token', {
                path: request.path,
                ip: request.ip,
            });
            throw new UnauthorizedException();
        }
        try {
            const payload = jwt.verify(token, process.env.JWT_SECRET);
            request.user = payload;
            this.logger.info('User authenticated', {
                user_id: payload.user_id,
                path: request.path,
            });
            return true;
        } catch (err) {
            this.logger.warn('Token verification failed', {
                path: request.path,
                ip: request.ip,
                error: err.message,
            });
            throw new UnauthorizedException();
        }
    }
}

@Controller('/admin')
export class AdminController {
    @UseGuards(AuthGuard)
    @Get('/users')
    listUsers() {
        return { users: [] };
    }
}
```

Inject the Logger service and log auth attempts, successes, and
failures.

## Permission check decorator without logging

### Vulnerable

```typescript
export function RequirePermission(permission: string) {
    return function (
        target: object,
        propertyKey: string,
        descriptor: PropertyDescriptor
    ) {
        const originalMethod = descriptor.value;
        descriptor.value = function (req: any, ...args: any[]) {
            if (!req.user?.permissions.includes(permission)) {
                throw new ForbiddenException();
            }
            return originalMethod.apply(this, args);
        };
        return descriptor;
    };
}

@Controller('/admin')
export class AdminController {
    @RequirePermission('admin')
    @Delete('/users/:id')
    deleteUser(@Param('id') userId: string) {
        return { status: 'deleted' };
    }
}
```

### Safe

```typescript
import { Logger } from '@nestjs/common';

const logger = new Logger('RequirePermission');

export function RequirePermission(permission: string) {
    return function (
        target: object,
        propertyKey: string,
        descriptor: PropertyDescriptor
    ) {
        const originalMethod = descriptor.value;
        descriptor.value = function (req: any, ...args: any[]) {
            if (!req.user?.permissions.includes(permission)) {
                logger.warn('Permission denied', {
                    user_id: req.user?.id,
                    permission,
                    path: req.path,
                    ip: req.ip,
                });
                throw new ForbiddenException();
            }
            logger.info('Permission granted', {
                user_id: req.user.id,
                permission,
                path: req.path,
            });
            return originalMethod.apply(this, args);
        };
        return descriptor;
    };
}

@Controller('/admin')
export class AdminController {
    @RequirePermission('admin')
    @Delete('/users/:id')
    deleteUser(@Param('id') userId: string) {
        return { status: 'deleted' };
    }
}
```

Log permission denials and approvals with user identity and resource
being accessed.

## Admin operation without audit logging

### Vulnerable

```typescript
@Controller('/admin/api')
export class AdminController {
    constructor(private userService: UserService) {}

    @Post('/users')
    async createUser(@Body() data: CreateUserDto) {
        const user = await this.userService.create(data);
        return { id: user.id };
    }

    @Delete('/users/:id')
    async deleteUser(@Param('id') userId: string) {
        await this.userService.delete(userId);
        return { status: 'deleted' };
    }
}
```

### Safe

```typescript
import { Logger } from '@nestjs/common';

@Controller('/admin/api')
export class AdminController {
    private logger = new Logger(AdminController.name);

    constructor(private userService: UserService) {}

    @Post('/users')
    async createUser(@Body() data: CreateUserDto, @Req() req: any) {
        const user = await this.userService.create(data);
        this.logger.info('User created by admin', {
            admin_id: req.user.id,
            created_user_id: user.id,
            email: user.email,
            ip: req.ip,
        });
        return { id: user.id };
    }

    @Delete('/users/:id')
    async deleteUser(
        @Param('id') userId: string,
        @Req() req: any
    ) {
        await this.userService.delete(userId);
        this.logger.info('User deleted by admin', {
            admin_id: req.user.id,
            deleted_user_id: userId,
            ip: req.ip,
        });
        return { status: 'deleted' };
    }
}
```

Log all admin state-changing operations with the acting admin's ID,
timestamp, and action details.

## Async auth without proper logging

### Vulnerable

```typescript
async function checkAuth(request: Request): Promise<User> {
    const token = request.headers.authorization?.split(' ')[1];
    const user = await User.findByToken(token);
    return user;
}

@Controller('/protected')
export class ProtectedController {
    @Get()
    async getResource(req: Request) {
        const user = await checkAuth(req);
        if (!user) {
            throw new UnauthorizedException();
        }
        return { resource: 'data' };
    }
}
```

### Safe

```typescript
import { Logger } from '@nestjs/common';

const logger = new Logger('AuthService');

async function checkAuth(request: Request): Promise<User> {
    const token = request.headers.authorization?.split(' ')[1];
    if (!token) {
        logger.warn('Auth attempt without token', {
            path: request.path,
            ip: request.ip,
        });
        throw new UnauthorizedException();
    }
    const user = await User.findByToken(token);
    if (!user) {
        logger.warn('Invalid token provided', {
            path: request.path,
            ip: request.ip,
        });
        throw new UnauthorizedException();
    }
    logger.info('User authenticated', {
        user_id: user.id,
        path: request.path,
    });
    return user;
}

@Controller('/protected')
export class ProtectedController {
    @Get()
    async getResource(req: Request) {
        const user = await checkAuth(req);
        return { resource: 'data' };
    }
}
```

Log auth failures with error details. Let the exception propagate with
proper logging.

## Express middleware with typed params without logging

### Vulnerable

```typescript
type AuthMiddleware = (
    req: Request,
    res: Response,
    next: NextFunction
) => void;

const authMiddleware: AuthMiddleware = (req, res, next) => {
    const token = req.headers.authorization?.split(' ')[1];
    if (!token) {
        return res.status(401).send({ error: 'Missing token' });
    }
    try {
        const payload = jwt.verify(token, process.env.SECRET);
        (req as any).user = payload;
        next();
    } catch (err) {
        return res.status(401).send({ error: 'Invalid token' });
    }
};

app.use(authMiddleware);
```

### Safe

```typescript
import winston from 'winston';

type AuthMiddleware = (
    req: Request,
    res: Response,
    next: NextFunction
) => void;

const logger = winston.createLogger({...});

const authMiddleware: AuthMiddleware = (req, res, next) => {
    const token = req.headers.authorization?.split(' ')[1];
    if (!token) {
        logger.warn('Missing token', {
            path: req.path,
            ip: req.ip,
        });
        return res.status(401).send({ error: 'Missing token' });
    }
    try {
        const payload = jwt.verify(token, process.env.SECRET);
        (req as any).user = payload;
        logger.info('User authenticated', {
            user_id: payload.user_id,
            path: req.path,
        });
        next();
    } catch (err) {
        logger.warn('Token verification failed', {
            path: req.path,
            ip: req.ip,
            error: (err as Error).message,
        });
        return res.status(401).send({ error: 'Invalid token' });
    }
};

app.use(authMiddleware);
```

Log auth attempts (success and failure) with user identity and client
IP.

## Fastify hook without logging

### Vulnerable

```typescript
import fastify from 'fastify';

const app = fastify();

app.addHook('onRequest', async (request, reply) => {
    const token = request.headers.authorization?.split(' ')[1];
    if (!token) {
        reply.status(401);
        return reply.send({ error: 'Missing token' });
    }
    try {
        const payload = jwt.verify(token, SECRET);
        (request as any).user = payload;
    } catch (err) {
        reply.status(401);
        return reply.send({ error: 'Invalid token' });
    }
});

app.get('/admin', async (request, reply) => {
    const user = (request as any).user;
    if (!user?.isAdmin) {
        reply.status(403);
        return reply.send({ error: 'Not admin' });
    }
    reply.send({ data: 'Admin panel' });
});
```

### Safe

```typescript
import fastify from 'fastify';
import pino from 'pino';

const app = fastify();
const logger = pino();

app.addHook('onRequest', async (request, reply) => {
    const token = request.headers.authorization?.split(' ')[1];
    if (!token) {
        logger.warn(
            { path: request.url, ip: request.ip },
            'Missing auth token'
        );
        reply.status(401);
        return reply.send({ error: 'Missing token' });
    }
    try {
        const payload = jwt.verify(token, SECRET);
        (request as any).user = payload;
        logger.info(
            { user_id: payload.user_id, path: request.url },
            'User authenticated'
        );
    } catch (err) {
        logger.warn(
            { path: request.url, ip: request.ip, error: (err as Error).message },
            'Token verification failed'
        );
        reply.status(401);
        return reply.send({ error: 'Invalid token' });
    }
});

app.get('/admin', async (request, reply) => {
    const user = (request as any).user;
    if (!user?.isAdmin) {
        logger.warn(
            { user_id: user.id, path: request.url },
            'Non-admin access to admin endpoint'
        );
        reply.status(403);
        return reply.send({ error: 'Not admin' });
    }
    logger.info({ user_id: user.id }, 'Admin endpoint accessed');
    reply.send({ data: 'Admin panel' });
});
```

Log all auth checks and admin resource access with user identity and
timestamp.
