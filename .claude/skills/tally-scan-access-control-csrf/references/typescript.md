# TypeScript CSRF patterns

Vulnerable-vs-safe snippets for the TypeScript frameworks the
`access_control.csrf` scanner recognizes. When multiple safe forms exist,
the canonical one is shown first.

## NestJS

### Vulnerable

```typescript
import { Controller, Post, Body } from '@nestjs/common';

@Controller('user')
export class UserController {
    @Post('update')
    async updateUser(@Body() data: { name: string }) {
        const user = await this.userService.getUser();
        user.name = data.name;
        await user.save();
        return { status: 'ok' };
    }
}
```

### Safe

```typescript
import { Controller, Post, Body, UseGuards, Get } from '@nestjs/common';
import { CsrfGuard } from '@nestjs/security';

@Controller('user')
export class UserController {
    @Get()
    async getUser(@Req() request) {
        // NestJS CsrfGuard generates a token automatically
        return { token: request.csrfToken() };
    }

    @Post('update')
    @UseGuards(CsrfGuard)
    async updateUser(@Body() data: { name: string; _csrf: string }) {
        const user = await this.userService.getUser();
        user.name = data.name;
        await user.save();
        return { status: 'ok' };
    }
}
```

Install `@nestjs/security` and register `CsrfGuard` on state-changing
routes:

```typescript
import { Module } from '@nestjs/common';
import { APP_GUARD } from '@nestjs/core';
import { CsrfGuard } from '@nestjs/security';

@Module({
    providers: [
        {
            provide: APP_GUARD,
            useClass: CsrfGuard,
        },
    ],
})
export class AppModule {}
```

The guard validates the CSRF token on POST/PUT/DELETE requests
automatically.

## Fastify

### Vulnerable

```typescript
import Fastify from 'fastify';

const app = Fastify();

app.post('/user/update', async (request, reply) => {
    const { name } = request.body as { name: string };
    const user = await getUser();
    user.name = name;
    await user.save();
    reply.send({ status: 'ok' });
});

app.listen({ port: 3000 });
```

### Safe

```typescript
import Fastify from 'fastify';
import fastifyCsrfProtection from '@fastify/csrf-protection';

const app = Fastify();
await app.register(fastifyCsrfProtection);

app.get('/user', async (request, reply) => {
    reply.send(`
        <form action="/user/update" method="POST">
            <input type="hidden" name="_csrf"
                value="${await request.csrfToken()}">
            <input type="text" name="name">
            <input type="submit">
        </form>
    `);
});

app.post('/user/update', async (request, reply) => {
    const { name } = request.body as { name: string };
    const user = await getUser();
    user.name = name;
    await user.save();
    reply.send({ status: 'ok' });
});

app.listen({ port: 3000 });
```

Install `@fastify/csrf-protection` and register it:

```typescript
await app.register(fastifyCsrfProtection);
```

The plugin validates the token on POST/PUT/DELETE requests automatically
and provides `request.csrfToken()` for templates.

## Express + TypeScript

### Vulnerable

```typescript
import express from 'express';
const app = express();

app.post('/user/update', (req: express.Request, res: express.Response) => {
    const { name } = req.body as { name: string };
    const user = getUser();
    user.name = name;
    user.save();
    res.json({ status: 'ok' });
});
```

### Safe

```typescript
import express from 'express';
import cookieParser from 'cookie-parser';
import csurf from 'csurf';

const app = express();

app.use(express.urlencoded({ extended: false }));
app.use(cookieParser());
app.use(csurf({ cookie: true }));

app.get('/user', (req: express.Request, res: express.Response) => {
    res.send(`
        <form action="/user/update" method="POST">
            <input type="hidden" name="_csrf" value="${req.csrfToken()}">
            <input type="text" name="name">
            <input type="submit">
        </form>
    `);
});

app.post(
    '/user/update',
    (req: express.Request, res: express.Response) => {
        const { name } = req.body as { name: string };
        const user = getUser();
        user.name = name;
        user.save();
        res.json({ status: 'ok' });
    }
);

app.listen(3000);
```

The pattern is identical to the JavaScript version. Register the `csurf`
middleware: `app.use(csurf({ cookie: true }))`. Call `req.csrfToken()` in
templates and the middleware validates the token on POST automatically.
