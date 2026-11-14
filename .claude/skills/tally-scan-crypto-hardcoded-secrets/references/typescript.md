# TypeScript hardcoded secrets patterns

Vulnerable and safe snippets for TypeScript secret management
that the `crypto.hardcoded_secrets` scanner recognizes.

## Typed config with hardcoded values

### Vulnerable

```typescript
interface AppConfig {
  apiKey: string;
  dbPassword: string;
}

const config: AppConfig = {
  apiKey: 'sk-proj-abc123',
  dbPassword: 'hunter2',
};
```

### Safe

```typescript
function requiredEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing env var: ${name}`);
  }
  return value;
}

const config: AppConfig = {
  apiKey: requiredEnv('API_KEY'),
  dbPassword: requiredEnv('DB_PASSWORD'),
};
```

## API keys and tokens

### Vulnerable

```typescript
const API_KEY: string = 'sk-proj-abc123def456';
```

### Safe

```typescript
const API_KEY: string = requiredEnv('API_KEY');
```

Same patterns as JavaScript. Load from environment, fail
fast when missing.
