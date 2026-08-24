# TypeScript framework defaults patterns

Vulnerable-vs-safe snippets for TypeScript framework default settings the
`misconfig.framework_defaults` scanner recognizes. When multiple safe
forms exist, the canonical one is shown first.

## NestJS ConfigModule debug flag

### Vulnerable

```typescript
// app.module.ts
import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';

@Module({
  imports: [
    ConfigModule.forRoot({
      debug: true,  // Hardcoded in production
      isGlobal: true
    })
  ]
})
export class AppModule {}
```

### Safe

```typescript
// app.module.ts
import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';

@Module({
  imports: [
    ConfigModule.forRoot({
      debug: process.env.NODE_ENV !== 'production',
      isGlobal: true
    })
  ]
})
export class AppModule {}

// or
ConfigModule.forRoot({
  debug: false,  // Explicit safe default
  isGlobal: true
})
```

Set `debug` based on `NODE_ENV`. Never hardcode `debug: true` in
production-bound code paths.

## NestJS default secrets

### Vulnerable

```typescript
// config/auth.config.ts
export const authConfig = {
  jwt: {
    secret: 'default-secret',  // Hardcoded
    expiresIn: '24h'
  },
  session: {
    secret: 'session-default'  // Hardcoded
  }
};

// or in auth.guard.ts
const secret = process.env.JWT_SECRET || 'insecure-default';
```

### Safe

```typescript
// config/auth.config.ts
export const authConfig = {
  jwt: {
    secret: process.env.JWT_SECRET,  // Required env var
    expiresIn: '24h'
  },
  session: {
    secret: process.env.SESSION_SECRET  // Required env var
  }
};

// Ensure the application fails to start if secrets are not set
if (!process.env.JWT_SECRET) {
  throw new Error('JWT_SECRET is required');
}
```

Load JWT_SECRET and session secrets from environment variables without
fallbacks to hardcoded defaults. Fail fast if the variable is missing.

## Express with TypeScript NODE_ENV

### Vulnerable

```typescript
// app.ts
import express from 'express';

const app = express();

// NODE_ENV not checked or hardcoded
const isDevelopment = true;  // Hardcoded in production
```

### Safe

```typescript
// app.ts
import express from 'express';

const app = express();
const isDevelopment = process.env.NODE_ENV !== 'production';

app.listen(3000);
```

Set `NODE_ENV=production` in the deployment environment. Load the
development flag from the environment variable.

## Express with TypeScript error handler

### Vulnerable

```typescript
// error.middleware.ts
import { Request, Response, NextFunction } from 'express';

export const errorMiddleware = (
  error: Error,
  req: Request,
  res: Response,
  next: NextFunction
) => {
  // Sends detailed error to client in production
  res.status(500).json({
    error: error.message,
    stack: error.stack  // Production risk
  });
};
```

### Safe

```typescript
// error.middleware.ts
import { Request, Response, NextFunction } from 'express';

export const errorMiddleware = (
  error: Error,
  req: Request,
  res: Response,
  next: NextFunction
) => {
  const isDevelopment = process.env.NODE_ENV !== 'production';
  res.status(500).json({
    message: isDevelopment ? error.message : 'Internal server error'
    // Do not send stack trace in production
  });
};
```

Never send stack traces to clients in production. Use environment checks
to return safe error responses.

## Next.js with TypeScript debug flags

### Vulnerable

```typescript
// next.config.ts
import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  productionBrowserSourceMaps: true,  // Production risk
  experimental: {
    debug: true  // Hardcoded
  }
};

export default nextConfig;
```

### Safe

```typescript
// next.config.ts
import type { NextConfig } from 'next';

const isDevelopment = process.env.NODE_ENV !== 'production';

const nextConfig: NextConfig = {
  productionBrowserSourceMaps: isDevelopment,
  experimental: {
    debug: isDevelopment
  }
};

export default nextConfig;
```

Load debug flags from `NODE_ENV`. Never hardcode production-risky settings
like `productionBrowserSourceMaps: true`.

## NestJS application hardcoded config values

### Vulnerable

```typescript
// config/database.config.ts
export const databaseConfig = {
  host: 'localhost',  // Development value
  port: 5432,
  username: 'dev_user',  // Development credentials
  password: 'dev_password',
  database: 'dev_db'
};

// Used in all environments without checking NODE_ENV
```

### Safe

```typescript
// config/database.config.ts
export const databaseConfig = {
  host: process.env.DB_HOST,
  port: parseInt(process.env.DB_PORT || '5432'),
  username: process.env.DB_USER,
  password: process.env.DB_PASSWORD,
  database: process.env.DB_NAME,
  // Fail fast if required variables are missing
  ...(process.env.NODE_ENV === 'production' && {
    ssl: process.env.DB_SSL === 'true'
  })
};

// Validate at application startup
if (!process.env.DB_HOST) {
  throw new Error('DB_HOST is required');
}
```

Load all configuration from environment variables. Never hardcode
development values (localhost, dev_user, dev_password) in production
code paths.
