# TypeScript file permissions patterns

Vulnerable-vs-safe snippets for insecure file permission operations the
`misconfig.insecure_file_permissions` scanner recognizes. When multiple
safe forms exist, the canonical one is shown first.

## fs.writeFileSync with overly permissive mode

### Vulnerable

```typescript
import * as fs from 'fs';

// Credential file with world-readable permissions
fs.writeFileSync('secrets.txt', secretData, {mode: 0o777});

// Config file
fs.writeFileSync('config.json', configData, {mode: 0o666});

// Or without mode: defaults to system umask
fs.writeFileSync('api_keys.txt', apiKeys);

interface FileOptions {
    mode: number;
}
const opts: FileOptions = {mode: 0o777};
fs.writeFileSync(keyFile, key, opts);
```

### Safe

```typescript
import * as fs from 'fs';

// Credential file: owner read/write only
fs.writeFileSync('secrets.txt', secretData, {mode: 0o600});

// Config file: owner read/write, group read
fs.writeFileSync('config.json', configData, {mode: 0o640});

// Type-safe secure write
interface SecureFileOptions {
    mode: 0o600 | 0o640;
}
const opts: SecureFileOptions = {mode: 0o600};
fs.writeFileSync(keyFile, key, opts);

// Helper function with type safety
function writeSecureFile(
    path: string,
    data: string,
    permissions: 0o600 | 0o640 = 0o600
): void {
    fs.writeFileSync(path, data, {mode: permissions});
}

writeSecureFile('secrets.txt', secretData);
```

Always specify a restrictive `mode` option (0o600 or 0o640) when writing
credential or config files. Use type-safe helpers to enforce secure defaults
across the codebase.

## fs.chmodSync with overly permissive mode

### Vulnerable

```typescript
import * as fs from 'fs';

// Make credential file world-readable
fs.chmodSync('secrets.txt', 0o777);

// Config file
fs.chmodSync('/etc/app/config.json', 0o666);

// Type mismatch but still compiled
type PermissionMode = number;
const insecureMode: PermissionMode = 0o777;
fs.chmodSync(keyFile, insecureMode);
```

### Safe

```typescript
import * as fs from 'fs';

// Credential file: owner read/write only
fs.chmodSync('secrets.txt', 0o600);

// Config file: owner read/write, group read
fs.chmodSync('/etc/app/config.json', 0o640);

// Type-safe permission mode
type SecurePermission = 0o600 | 0o640 | 0o700;

function setSecurePermissions(
    path: string,
    mode: SecurePermission = 0o600
): void {
    fs.chmodSync(path, mode);
}

setSecurePermissions('secrets.txt');
```

Use typed permission constants to prevent accidental overly permissive
modes. Create helper functions that enforce secure defaults.

## fs.mkdtempSync without restrictive mode

### Vulnerable

```typescript
import * as fs from 'fs';

// Create temp directory without mode: inherits system umask
const tmpDir: string = fs.mkdtempSync('app_');

// Or with permissive mode
const tmpDir2: string = fs.mkdtempSync('app_', {mode: 0o777});

// Subsequent files may be world-readable
fs.writeFileSync(`${tmpDir}/secrets.txt`, secretData);
```

### Safe

```typescript
import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';

// Create temp directory with owner-only permissions
const tmpDir: string = fs.mkdtempSync('app_', {mode: 0o700});

// Subsequent files inherit directory permissions
fs.writeFileSync(`${tmpDir}/secrets.txt`, secretData, {mode: 0o600});

// Type-safe temp directory helper
type TempDirMode = 0o700;

function createSecureTempDir(prefix: string): string {
    const tmpDir = fs.mkdtempSync(
        path.join(os.tmpdir(), prefix),
        {mode: 0o700 as TempDirMode}
    );
    return tmpDir;
}

function withSecureTempDir<T>(
    prefix: string,
    callback: (tmpDir: string) => T
): T {
    const tmpDir = createSecureTempDir(prefix);
    try {
        return callback(tmpDir);
    } finally {
        fs.rmSync(tmpDir, {recursive: true, force: true});
    }
}

// Usage
withSecureTempDir('app_', (tmpDir) => {
    fs.writeFileSync(`${tmpDir}/secrets.txt`, secretData, {mode: 0o600});
});
```

Always specify `mode: 0o700` when creating temp directories. Use type-safe
helpers to enforce secure patterns across the codebase. Use try-finally or
context managers to ensure cleanup.

## Secrets written to files

### Vulnerable

```typescript
import * as fs from 'fs';

// Writing API key without mode control
fs.writeFileSync('api_key.txt', apiKey);

// Token stored without permissions
interface AuthToken {
    token: string;
    expires: number;
}
const authToken: AuthToken = {token, expires};
fs.writeFileSync('auth_token.json', JSON.stringify(authToken));

// Using promises without permissions
async function saveCredentials(creds: string): Promise<void> {
    await fs.promises.writeFile('credentials.txt', creds);
}

// Appending secrets
fs.appendFileSync('secrets.txt', newSecret + '\n');
```

### Safe

```typescript
import * as fs from 'fs';

// Write API key with restrictive permissions
fs.writeFileSync('api_key.txt', apiKey, {mode: 0o600});

// Token stored securely
interface AuthToken {
    token: string;
    expires: number;
}
const authToken: AuthToken = {token, expires};
fs.writeFileSync('auth_token.json', JSON.stringify(authToken), {
    mode: 0o600
});

// Type-safe async secure write
async function saveCredentials(creds: string): Promise<void> {
    await fs.promises.writeFile('credentials.txt', creds, {mode: 0o600});
}

// Helper with type safety
interface SecretData {
    content: string;
    type: 'credential' | 'token' | 'key';
}

async function saveSecretData(
    path: string,
    data: SecretData
): Promise<void> {
    const json = JSON.stringify(data);
    await fs.promises.writeFile(path, json, {mode: 0o600});
}

// Appending with explicit mode and verification
function appendSecret(path: string, secret: string): void {
    const flags = fs.existsSync(path) ? 'a' : 'w';
    fs.writeFileSync(path, secret + '\n', {flag: flags, mode: 0o600});
    // Verify permissions
    fs.chmodSync(path, 0o600);
}
```

Always specify `mode: 0o600` when writing files containing credentials,
API keys, tokens, or secrets. Use type-safe helpers to enforce secure
defaults across the application. Verify file permissions after write
operations.
