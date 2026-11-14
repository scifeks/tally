# TypeScript missing exception handling patterns

Vulnerable-vs-safe snippets for TypeScript auth guards (NestJS),
async middleware, decorators, and Fastify hooks.

## NestJS guard with global exception filter fail-open

### Vulnerable

```typescript
@Injectable()
export class AuthGuard implements CanActivate {
    canActivate(context: ExecutionContext): boolean {
        const request = context.switchToHttp().getRequest();
        const token = request.headers.authorization?.split(' ')[1];
        const payload = jwt.verify(token, process.env.JWT_SECRET);
        return !!payload;
    }
}

@UseGuards(AuthGuard)
@Controller('/admin')
export class AdminController {
    @Get()
    listUsers() {
        return { users: [] };
    }
}

@Injectable()
export class GlobalExceptionFilter implements ExceptionFilter {
    catch(exception: Exception, host: ArgumentsHost) {
        const ctx = host.switchToHttp();
        const response = ctx.getResponse();
        response.status(200).json({ error: 'Something went wrong' });
    }
}
```

The guard throws when JWT verification fails, but the global exception
filter catches all exceptions and returns HTTP 200.

### Safe

```typescript
@Injectable()
export class AuthGuard implements CanActivate {
    canActivate(context: ExecutionContext): boolean {
        const request = context.switchToHttp().getRequest();
        const token = request.headers.authorization?.split(' ')[1];
        if (!token) {
            throw new UnauthorizedException('Missing token');
        }
        try {
            const payload = jwt.verify(token, process.env.JWT_SECRET);
            return !!payload;
        } catch (err) {
            throw new UnauthorizedException('Invalid token');
        }
    }
}

@UseFilters(new GlobalExceptionFilter())
@Controller('/admin')
export class AdminController {
    @Get()
    listUsers() {
        return { users: [] };
    }
}

@Injectable()
export class GlobalExceptionFilter implements ExceptionFilter {
    catch(exception: Exception, host: ArgumentsHost) {
        const ctx = host.switchToHttp();
        const response = ctx.getResponse();
        if (exception instanceof UnauthorizedException) {
            response.status(401).json({ error: 'Unauthorized' });
        } else {
            response.status(500).json({ error: 'Server error' });
        }
    }
}
```

The guard throws UnauthorizedException, and the global filter maps it to
401. Never map auth exceptions to 200.

## Async auth without await

### Vulnerable

```typescript
async function checkAuth(req: Request): Promise<User> {
    const token = req.headers.authorization?.split(' ')[1];
    return User.findByToken(token);  // Returns a promise
}

@Controller('/protected')
export class ProtectedController {
    @Get()
    getResource(req: Request) {
        const user = checkAuth(req);  // user is a Promise, not a User
        if (!user) {
            throw new UnauthorizedException();
        }
        return { resource: 'data' };
    }
}
```

The middleware is async but the route handler does not await. The
promise is pending when the route executes.

### Safe

```typescript
async function checkAuth(req: Request): Promise<User> {
    const token = req.headers.authorization?.split(' ')[1];
    if (!token) {
        throw new UnauthorizedException('Missing token');
    }
    const user = await User.findByToken(token);
    if (!user) {
        throw new UnauthorizedException('Invalid token');
    }
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

Await the promise. Mark the route handler as async.

## Decorator wrapping permission check with catch

### Vulnerable

```typescript
export function RequirePermission(permission: string) {
    return function (
        target: object,
        propertyKey: string,
        descriptor: PropertyDescriptor
    ) {
        const originalMethod = descriptor.value;
        descriptor.value = function (...args: any[]) {
            try {
                const user = getCurrentUser();
                if (!user.hasPermission(permission)) {
                    throw new ForbiddenException();
                }
            } catch (err) {
                // Exception caught; method still executes
                return { error: 'Permission denied' };
            }
            return originalMethod.apply(this, args);
        };
        return descriptor;
    };
}

@Controller('/admin')
export class AdminController {
    @RequirePermission('admin')
    @Get()
    deleteAllUsers() {
        User.deleteAll();
        return { message: 'All users deleted' };
    }
}
```

### Safe

```typescript
export function RequirePermission(permission: string) {
    return function (
        target: object,
        propertyKey: string,
        descriptor: PropertyDescriptor
    ) {
        const originalMethod = descriptor.value;
        descriptor.value = function (...args: any[]) {
            const user = getCurrentUser();
            if (!user || !user.hasPermission(permission)) {
                throw new ForbiddenException(
                    `Requires ${permission} permission`
                );
            }
            return originalMethod.apply(this, args);
        };
        return descriptor;
    };
}

@Controller('/admin')
export class AdminController {
    @RequirePermission('admin')
    @Get()
    deleteAllUsers() {
        User.deleteAll();
        return { message: 'All users deleted' };
    }
}
```

Throw directly. Do not catch permission exceptions.

## Fastify hook with fail-open error handling

### Vulnerable

```typescript
import fastify from 'fastify';

const app = fastify();

app.addHook('onRequest', async (request, reply) => {
    try {
        const token = request.headers.authorization?.split(' ')[1];
        const payload = jwt.verify(token, SECRET);
        (request as any).user = payload;
    } catch (err) {
        reply.code(200);  // Returns 200 on auth failure
    }
});

app.get('/admin', async (request, reply) => {
    const user = (request as any).user;
    if (!user?.isAdmin) {
        reply.code(403);
        return { error: 'Not admin' };
    }
    reply.send({ data: 'Admin panel' });
});
```

### Safe

```typescript
import fastify from 'fastify';

const app = fastify();

app.addHook('onRequest', async (request, reply) => {
    try {
        const token = request.headers.authorization?.split(' ')[1];
        if (!token) {
            reply.code(401);
            return reply.send({ error: 'Missing token' });
        }
        const payload = jwt.verify(token, SECRET);
        (request as any).user = payload;
    } catch (err) {
        reply.code(401);
        return reply.send({ error: 'Invalid token' });
    }
});

app.get('/admin', async (request, reply) => {
    const user = (request as any).user;
    if (!user?.isAdmin) {
        reply.code(403);
        return { error: 'Not admin' };
    }
    reply.send({ data: 'Admin panel' });
});
```

Call `reply.send()` in the error path to prevent the route handler from
executing.

## Express middleware with typed fail-open

### Vulnerable

```typescript
type AuthMiddleware = (
    req: Request,
    res: Response,
    next: NextFunction
) => void;

const authMiddleware: AuthMiddleware = (req, res, next) => {
    try {
        const token = req.headers.authorization?.split(' ')[1] || '';
        const payload = jwt.verify(token, SECRET);
        (req as any).user = payload;
    } catch (err) {
        next();  // next() without error; request proceeds
    }
};

app.use(authMiddleware);
app.get('/admin', (req: Request, res: Response) => {
    const user = (req as any).user;
    if (!user?.isAdmin) {
        return res.status(403).send('Not admin');
    }
    res.send('Admin panel');
});
```

### Safe

```typescript
type AuthMiddleware = (
    req: Request,
    res: Response,
    next: NextFunction
) => void;

const authMiddleware: AuthMiddleware = (req, res, next) => {
    try {
        const token = req.headers.authorization?.split(' ')[1];
        if (!token) {
            return res.status(401).send('Missing token');
        }
        const payload = jwt.verify(token, SECRET);
        (req as any).user = payload;
        next();
    } catch (err) {
        res.status(401).send('Invalid token');
    }
};

app.use(authMiddleware);
app.get('/admin', (req: Request, res: Response) => {
    const user = (req as any).user;
    if (!user?.isAdmin) {
        return res.status(403).send('Not admin');
    }
    res.send('Admin panel');
});
```

Return a 401 response in the catch block. Call `next()` only after a
successful auth check.

## Async guard with unhandled rejection

### Vulnerable

```typescript
@Injectable()
export class AsyncAuthGuard implements CanActivate {
    async canActivate(context: ExecutionContext): Promise<boolean> {
        const request = context.switchToHttp().getRequest();
        const token = request.headers.authorization?.split(' ')[1];
        const payload = await jwt.verify(token, SECRET);
        return !!payload;
        // If promise rejects, exception propagates unhandled
    }
}
```

### Safe

```typescript
@Injectable()
export class AsyncAuthGuard implements CanActivate {
    async canActivate(context: ExecutionContext): Promise<boolean> {
        try {
            const request = context.switchToHttp().getRequest();
            const token = request.headers.authorization?.split(' ')[1];
            if (!token) {
                throw new UnauthorizedException('Missing token');
            }
            const payload = await jwt.verify(token, SECRET);
            return !!payload;
        } catch (err) {
            throw new UnauthorizedException('Invalid token');
        }
    }
}
```

Wrap async operations in try/catch. Throw the appropriate exception type
so NestJS maps it to the correct HTTP status.
