# JavaScript hardcoded secrets patterns

Vulnerable and safe snippets for Node.js secret management
that the `crypto.hardcoded_secrets` scanner recognizes.

## API keys and tokens

### Vulnerable

```javascript
const API_KEY = 'sk-proj-abc123def456';
const token = 'ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxx';
const password = 'admin123';
```

### Safe

```javascript
const API_KEY = process.env.API_KEY;
const token = process.env.GITHUB_TOKEN;
```

## Fallback literals

### Vulnerable

```javascript
const secret = process.env.SECRET || 'default-secret';
```

### Safe

```javascript
const secret = process.env.SECRET;
if (!secret) {
  throw new Error('SECRET env var is required');
}
```

Fallback literals defeat the purpose of environment-based
configuration. Fail fast when a required secret is missing.

## Firebase config

### Vulnerable

```javascript
const firebaseConfig = {
  apiKey: 'AIzaSyDxxxxxxxxxxxxxxxxxxxxxxxxxx',
  authDomain: 'my-app.firebaseapp.com',
  projectId: 'my-app',
};
```

### Safe

```javascript
const firebaseConfig = {
  apiKey: process.env.FIREBASE_API_KEY,
  authDomain: process.env.FIREBASE_AUTH_DOMAIN,
  projectId: process.env.FIREBASE_PROJECT_ID,
};
```

## Connection strings

### Vulnerable

```javascript
const mongoUrl =
  'mongodb://admin:pass@prod.mongo.example.com/db';
```

### Safe

```javascript
const mongoUrl = process.env.MONGODB_URI;
```
