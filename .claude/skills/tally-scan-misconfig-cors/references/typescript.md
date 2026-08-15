# TypeScript CORS misconfiguration patterns

Vulnerable-vs-safe snippets for TypeScript web frameworks the
`misconfig.cors` scanner recognizes. When multiple safe forms exist, the
canonical one is shown first.

## Express with cors middleware

### Vulnerable

```typescript
import express from 'express';
import cors from 'cors';

const app = express();

app.use(cors({origin: '*', credentials: true}));
```

### Safe

```typescript
import express from 'express';
import cors, {CorsOptions} from 'cors';

const app = express();

const allowedOrigins: string[] = [
  'https://app.example.com',
  'https://trusted-partner.example.com',
];

const corsOptions: CorsOptions = {
  origin: allowedOrigins,
  credentials: true,
};

app.use(cors(corsOptions));
```

Define an explicit list of allowed origins. TypeScript type annotations do
not prevent misconfiguration, so validate origins at runtime.

## NestJS CORS configuration

### Vulnerable

```typescript
import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';

async function bootstrap() {
  const app = await NestFactory.create(AppModule);
  app.enableCors({origin: '*', credentials: true});
  await app.listen(3000);
}

bootstrap();
```

### Safe

```typescript
import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';

async function bootstrap() {
  const app = await NestFactory.create(AppModule);

  const allowedOrigins = [
    'https://app.example.com',
    'https://trusted-partner.example.com',
  ];

  app.enableCors({
    origin: allowedOrigins,
    credentials: true,
  });

  await app.listen(3000);
}

bootstrap();
```

Provide an explicit list of allowed origins to the enableCors method. When
credentials are enabled, enumerate origins instead of using wildcard.

## Fastify CORS plugin

### Vulnerable

```typescript
import Fastify from 'fastify';
import fastifyCors from '@fastify/cors';

const fastify = Fastify();

fastify.register(fastifyCors, {
  origin: '*',
  credentials: true,
});
```

### Safe

```typescript
import Fastify from 'fastify';
import fastifyCors from '@fastify/cors';

const fastify = Fastify();

const allowedOrigins = [
  'https://app.example.com',
  'https://trusted-partner.example.com',
];

fastify.register(fastifyCors, {
  origin: allowedOrigins,
  credentials: true,
});
```

Pass an array of allowed origins to the Fastify CORS plugin. Wildcard origin
with credentials is a misconfiguration and should be replaced with an
explicit allowlist.

## Custom CORS middleware with origin reflection

### Vulnerable

```typescript
import { Request, Response, NextFunction } from 'express';

export const corsMiddleware = (
  req: Request,
  res: Response,
  next: NextFunction,
) => {
  res.setHeader('Access-Control-Allow-Origin', req.headers.origin || '*');
  res.setHeader('Access-Control-Allow-Credentials', 'true');
  next();
};
```

### Safe

```typescript
import { Request, Response, NextFunction } from 'express';

const ALLOWED_ORIGINS: Set<string> = new Set([
  'https://app.example.com',
  'https://trusted-partner.example.com',
]);

export const corsMiddleware = (
  req: Request,
  res: Response,
  next: NextFunction,
) => {
  const origin = req.headers.origin;

  if (origin && ALLOWED_ORIGINS.has(origin)) {
    res.setHeader('Access-Control-Allow-Origin', origin);
    res.setHeader('Access-Control-Allow-Credentials', 'true');
  }

  next();
};
```

Validate the Origin header against an allowlist before reflecting it. Use a
Set for efficient lookup and never fall back to wildcard.

## TypeScript-first CORS validation

### Vulnerable

```typescript
interface CorsConfig {
  allowedOrigins: string[];
  credentialsEnabled: boolean;
}

const config: CorsConfig = {
  allowedOrigins: ['*'],
  credentialsEnabled: true,
};
```

### Safe

```typescript
interface CorsConfig {
  allowedOrigins: string[];
  credentialsEnabled: boolean;
}

const validateOrigin = (origin: string): boolean => {
  const allowed = [
    'https://app.example.com',
    'https://trusted-partner.example.com',
  ];
  return allowed.includes(origin);
};

const config: CorsConfig = {
  allowedOrigins: [
    'https://app.example.com',
    'https://trusted-partner.example.com',
  ],
  credentialsEnabled: true,
};
```

Use TypeScript interfaces to enforce explicit origin lists at compile time.
Implement runtime validation functions to check incoming origins against the
allowlist.
