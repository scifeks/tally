# TypeScript CSP misconfiguration patterns

Vulnerable-vs-safe snippets for TypeScript web frameworks the `misconfig.csp`
scanner recognizes. When multiple safe forms exist, the canonical one is
shown first.

## Express with helmet and TypeScript

### Vulnerable

```typescript
import express, { Express } from 'express';
import helmet from 'helmet';

const app: Express = express();
app.use(helmet({
  contentSecurityPolicy: false,
}));

// CSP is disabled
```

### Safe

```typescript
import express, { Express } from 'express';
import helmet from 'helmet';

const app: Express = express();
app.use(helmet({
  contentSecurityPolicy: {
    directives: {
      defaultSrc: ["'self'"],
      scriptSrc: ["'self'"],
      styleSrc: ["'self'", "https://fonts.googleapis.com"],
    },
  },
}));
```

Enable CSP in helmet by providing a config object with restrictive directives.
Set `defaultSrc` to `["'self'"]` and add specific sources for scripts and
styles.

## NestJS with helmet

### Vulnerable

```typescript
// main.ts
import { NestFactory } from '@nestjs/core';
import * as helmet from 'helmet';
import { AppModule } from './app.module';

async function bootstrap() {
  const app = await NestFactory.create(AppModule);
  app.use(helmet({
    contentSecurityPolicy: false,
  }));
  await app.listen(3000);
}

bootstrap();
```

### Safe

```typescript
// main.ts
import { NestFactory } from '@nestjs/core';
import * as helmet from 'helmet';
import { AppModule } from './app.module';

async function bootstrap() {
  const app = await NestFactory.create(AppModule);
  app.use(helmet({
    contentSecurityPolicy: {
      directives: {
        defaultSrc: ["'self'"],
        scriptSrc: ["'self'"],
        styleSrc: ["'self'", "https://fonts.googleapis.com"],
      },
    },
  }));
  await app.listen(3000);
}

bootstrap();
```

Register helmet with a restrictive CSP configuration before starting the
NestJS application. Set `defaultSrc` to `["'self'"]` and add specific sources
for scripts and styles.

## NestJS helmet permissive

### Vulnerable

```typescript
// main.ts
import { NestFactory } from '@nestjs/core';
import * as helmet from 'helmet';
import { AppModule } from './app.module';

async function bootstrap() {
  const app = await NestFactory.create(AppModule);
  app.use(helmet({
    contentSecurityPolicy: {
      directives: {
        defaultSrc: ["*"],
        scriptSrc: ["*", "'unsafe-inline'"],
      },
    },
  }));
  await app.listen(3000);
}

bootstrap();
```

### Safe

```typescript
// main.ts
import { NestFactory } from '@nestjs/core';
import * as helmet from 'helmet';
import { AppModule } from './app.module';

async function bootstrap() {
  const app = await NestFactory.create(AppModule);
  app.use(helmet({
    contentSecurityPolicy: {
      directives: {
        defaultSrc: ["'self'"],
        scriptSrc: ["'self'"],
        styleSrc: ["'self'", "https://fonts.googleapis.com"],
      },
    },
  }));
  await app.listen(3000);
}

bootstrap();
```

Replace wildcard sources with `'self'`. Remove `'unsafe-inline'` and
`'unsafe-eval'` unless the application requires them. Use a nonce-based
policy for inline content when possible.

## Custom middleware with TypeScript

### Vulnerable

```typescript
import { Request, Response, NextFunction } from 'express';

export function securityHeaders(
  req: Request,
  res: Response,
  next: NextFunction
): void {
  res.setHeader(
    'Content-Security-Policy',
    "default-src *; script-src * 'unsafe-inline'"
  );
  next();
}
```

### Safe

```typescript
import { Request, Response, NextFunction } from 'express';

export function securityHeaders(
  req: Request,
  res: Response,
  next: NextFunction
): void {
  const csp = (
    "default-src 'self'; "
    + "script-src 'self'; "
    + "style-src 'self' https://fonts.googleapis.com"
  );
  res.setHeader('Content-Security-Policy', csp);
  next();
}
```

Set a restrictive CSP header with `default-src 'self'` and add specific
sources for scripts and styles. Use this middleware in the Express app setup.
