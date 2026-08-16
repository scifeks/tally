# JavaScript file permissions patterns

Vulnerable-vs-safe snippets for insecure file permission operations the
`misconfig.insecure_file_permissions` scanner recognizes. When multiple
safe forms exist, the canonical one is shown first.

## fs.writeFileSync with overly permissive mode

### Vulnerable

```javascript
const fs = require('fs');

// Credential file with world-readable permissions
fs.writeFileSync('secrets.txt', secretData, {mode: 0o777});

// Config file
fs.writeFileSync('config.json', configData, {mode: 0o666});

// Or numeric form
fs.writeFileSync(keyFile, key, {mode: 0777});

// Without mode: defaults to system umask, may be world-readable
fs.writeFileSync('api_keys.txt', apiKeys);
```

### Safe

```javascript
const fs = require('fs');

// Credential file: owner read/write only
fs.writeFileSync('secrets.txt', secretData, {mode: 0o600});

// Config file: owner read/write, group read
fs.writeFileSync('config.json', configData, {mode: 0o640});

// Explicitly restrictive
fs.writeFileSync(keyFile, key, {mode: 0o600});
```

Always specify a restrictive `mode` option when writing credential or
config files. Use `mode: 0o600` to restrict to owner-only access, or
`mode: 0o640` for owner-read/write and group-read access.

## fs.chmodSync with overly permissive mode

### Vulnerable

```javascript
const fs = require('fs');

// Make credential file world-readable
fs.chmodSync('secrets.txt', 0o777);

// Config file
fs.chmodSync('/etc/app/config.json', 0o666);

// Or octal
fs.chmodSync(keyFile, 0777);
```

### Safe

```javascript
const fs = require('fs');

// Credential file: owner read/write only
fs.chmodSync('secrets.txt', 0o600);

// Config file: owner read/write, group read
fs.chmodSync('/etc/app/config.json', 0o640);

// Explicitly restrictive
fs.chmodSync(keyFile, 0o600);
```

Never grant world-read or world-write permissions to credential, config, or
secret files. Use `0o600` for owner-only access or `0o640` for
owner-read/write and group-read access.

## fs.mkdtempSync without restrictive mode

### Vulnerable

```javascript
const fs = require('fs');

// Create temp directory without mode: inherits system umask
const tmpDir = fs.mkdtempSync('app_');

// Or with permissive mode
const tmpDir = fs.mkdtempSync('app_', {mode: 0o777});

// Subsequent temp files may be world-readable
fs.writeFileSync(`${tmpDir}/secrets.txt`, secretData);
```

### Safe

```javascript
const fs = require('fs');

// Create temp directory with owner-only permissions
const tmpDir = fs.mkdtempSync('app_', {mode: 0o700});

// Subsequent files inherit directory permissions
fs.writeFileSync(`${tmpDir}/secrets.txt`, secretData);

// Or explicitly set file permissions
fs.writeFileSync(`${tmpDir}/secrets.txt`, secretData, {mode: 0o600});

// For a more complete pattern
const path = require('path');
const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'app_'));
fs.chmodSync(tmpDir, 0o700);
try {
    fs.writeFileSync(`${tmpDir}/secrets.txt`, secretData, {mode: 0o600});
    // Use temp directory...
} finally {
    fs.rmSync(tmpDir, {recursive: true, force: true});
}
```

Always specify `mode: 0o700` when creating temp directories to restrict to
owner-only access. Set restrictive permissions on files created within the
temp directory as well.

## Secrets written without permission control

### Vulnerable

```javascript
const fs = require('fs');

// Writing API key without mode control
fs.writeFileSync('api_key.txt', apiKey);

// Token stored without permissions
fs.writeFileSync('auth_token.json', JSON.stringify({token}));

// Or using promises
fs.promises.writeFile('credentials.txt', credentials);

// Appending secrets without permission control
fs.appendFileSync('secrets.txt', newSecret + '\n');
```

### Safe

```javascript
const fs = require('fs');

// Write API key with restrictive permissions
fs.writeFileSync('api_key.txt', apiKey, {mode: 0o600});

// Token stored securely
fs.writeFileSync('auth_token.json', JSON.stringify({token}), {
    mode: 0o600
});

// Using promises with explicit permissions
async function writeSecureFile(path, data) {
    await fs.promises.writeFile(path, data, {mode: 0o600});
}

// Or set permissions after write
fs.writeFileSync('credentials.txt', credentials);
fs.chmodSync('credentials.txt', 0o600);

// Appending with explicit mode
const flags = fs.existsSync('secrets.txt') ? 'a' : 'w';
fs.writeFileSync('secrets.txt', newSecret + '\n', {
    flag: flags,
    mode: 0o600
});

// After appending, verify permissions
fs.chmodSync('secrets.txt', 0o600);
```

Always specify `mode: 0o600` when writing files containing credentials,
API keys, tokens, or secrets. If appending to an existing file, verify the
file has restrictive permissions and update them if needed.
