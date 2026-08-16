# TypeScript missing security headers patterns

Vulnerable-vs-safe snippets for TypeScript web frameworks the
`misconfig.security_headers` scanner recognizes. When multiple safe forms
exist, the canonical one is shown first.

## NestJS without helmet

### Vulnerable

```typescript
import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';

async function bootstrap() {
    const app = await NestFactory.create(AppModule);
    await app.listen(3000);
}

bootstrap();
```

### Safe

```typescript
import { NestFactory } from '@nestjs/core';
import * as helmet from 'helmet';
import { AppModule } from './app.module';

async function bootstrap() {
    const app = await NestFactory.create(AppModule);
    app.use(helmet({
        hsts: { maxAge: 31536000, includeSubDomains: true },
        frameguard: { action: 'deny' },
        contentSecurityPolicy: false
    }));
    await app.listen(3000);
}

bootstrap();
```

Install helmet with npm install helmet. Import and call app.use(helmet())
in main.ts before listening. Helmet sets X-Content-Type-Options,
X-Frame-Options, Strict-Transport-Security, and Referrer-Policy headers
on all responses automatically.

## Express with TypeScript

### Vulnerable

```typescript
import express, { Express, Request, Response } from 'express';

const app: Express = express();

app.get('/api/user', (req: Request, res: Response) => {
    res.json({ id: 1, name: 'Alice' });
});

app.listen(3000);
```

### Safe

```typescript
import express, { Express, Request, Response } from 'express';
import helmet from 'helmet';

const app: Express = express();

app.use(helmet({
    hsts: { maxAge: 31536000, includeSubDomains: true },
    frameguard: { action: 'deny' }
}));

app.get('/api/user', (req: Request, res: Response) => {
    res.json({ id: 1, name: 'Alice' });
});

app.listen(3000);
```

Install @types/helmet with npm install @types/helmet for TypeScript
support. Call app.use(helmet()) without disabling individual protections.
Helmet sets X-Content-Type-Options, X-Frame-Options,
Strict-Transport-Security, and Referrer-Policy headers by default.

## Express middleware with TypeScript

### Vulnerable

```typescript
import { Request, Response, NextFunction } from 'express';

export function customMiddleware(
    req: Request,
    res: Response,
    next: NextFunction
) {
    res.setHeader('X-Custom-Header', 'value');
    next();
}
```

### Safe

```typescript
import { Request, Response, NextFunction } from 'express';

export function securityHeadersMiddleware(
    req: Request,
    res: Response,
    next: NextFunction
) {
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('X-Frame-Options', 'DENY');
    res.setHeader(
        'Strict-Transport-Security',
        'max-age=31536000; includeSubDomains'
    );
    res.setHeader(
        'Referrer-Policy',
        'strict-origin-when-cross-origin'
    );
    res.setHeader('X-Custom-Header', 'value');
    next();
}
```

Type the middleware with Request, Response, and NextFunction. Call
res.setHeader() to add X-Content-Type-Options, X-Frame-Options,
Strict-Transport-Security, and Referrer-Policy headers. Register the
middleware globally before defining routes.

## Fastify with TypeScript

### Vulnerable

```typescript
import Fastify from 'fastify';

const fastify = Fastify();

fastify.get('/api/user', async (request, reply) => {
    reply.send({ id: 1, name: 'Alice' });
});

fastify.listen({ port: 3000 });
```

### Safe

```typescript
import Fastify from 'fastify';
import helmet from '@fastify/helmet';

const fastify = Fastify();

fastify.register(helmet, {
    contentSecurityPolicy: false,
    hsts: { maxAge: 31536000, includeSubDomains: true },
    frameguard: { action: 'deny' }
});

fastify.get('/api/user', async (request, reply) => {
    reply.send({ id: 1, name: 'Alice' });
});

fastify.listen({ port: 3000 });
```

Install @fastify/helmet with npm install @fastify/helmet. Register the
plugin with fastify.register(helmet) before starting the server. The
plugin sets X-Content-Type-Options, X-Frame-Options,
Strict-Transport-Security, and Referrer-Policy headers on all responses.

## Custom NestJS middleware with typed response

### Vulnerable

```typescript
import { Injectable, NestMiddleware } from '@nestjs/common';
import { Request, Response, NextFunction } from 'express';

@Injectable()
export class CustomMiddleware implements NestMiddleware {
    use(req: Request, res: Response, next: NextFunction) {
        res.setHeader('X-Custom-Header', 'value');
        next();
    }
}
```

### Safe

```typescript
import { Injectable, NestMiddleware } from '@nestjs/common';
import { Request, Response, NextFunction } from 'express';

@Injectable()
export class SecurityHeadersMiddleware implements NestMiddleware {
    use(req: Request, res: Response, next: NextFunction) {
        res.setHeader('X-Content-Type-Options', 'nosniff');
        res.setHeader('X-Frame-Options', 'DENY');
        res.setHeader(
            'Strict-Transport-Security',
            'max-age=31536000; includeSubDomains'
        );
        res.setHeader(
            'Referrer-Policy',
            'strict-origin-when-cross-origin'
        );
        res.setHeader('X-Custom-Header', 'value');
        next();
    }
}

// app.module.ts
import { MiddlewareConsumer, Module, NestModule } from '@nestjs/common';
import { SecurityHeadersMiddleware } from './security-headers.middleware';

@Module({})
export class AppModule implements NestModule {
    configure(consumer: MiddlewareConsumer) {
        consumer.apply(SecurityHeadersMiddleware).forRoutes('*');
    }
}
```

Implement NestMiddleware with typed Request and Response. Call
res.setHeader() to add security headers. Register in app.module.ts using
configure() and MiddlewareConsumer.forRoutes() to apply globally.
