# TypeScript OS command injection patterns

Vulnerable-vs-safe snippets for the Node.js child_process patterns and the
`execa` library that the `injection.os_command` scanner recognizes. When
multiple safe forms exist, the canonical one is shown first.

## child_process patterns (same as JavaScript)

All JavaScript patterns apply directly on the Node.js runtime. Use
`execFile()` or `execFileSync()` with argument arrays; never use `exec()`
or `spawn('sh', ['-c', ...])` with user input.

### Vulnerable (exec with template literal)

```typescript
const userInput: string = req.query.command as string;
exec(`ls ${userInput}`, (error, stdout, stderr) => {
    console.log(stdout);
});
```

### Safe (execFile with argument array)

```typescript
const userInput: string = req.query.command as string;
execFile('ls', [userInput], (error, stdout, stderr) => {
    console.log(stdout);
});
```

## execa library

The `execa` library is a popular Node.js wrapper around child_process. It
is safer by default but can be exploited if `shell: true` is set with user
input.

### Vulnerable

```typescript
import {execa} from 'execa';

const userInput = req.query.filename;
const result = await execa('sh', ['-c', `cat ${userInput}`]);

const dir = req.query.directory;
const {stdout} = await execa(`ls ${dir}`, {shell: true});
```

### Safe

```typescript
import {execa} from 'execa';

const userInput = req.query.filename;
const result = await execa('cat', [userInput]);

const dir = req.query.directory;
const {stdout} = await execa('ls', [dir]);
```

Never set `shell: true` with user input. Pass arguments as an array.

## execa with options

### Vulnerable

```typescript
const pattern = req.body.search;
const result = await execa('grep', [pattern], {
    shell: true,
    stdio: 'inherit',
});
```

### Safe

```typescript
const pattern = req.body.search;
const result = await execa('grep', [pattern], {
    stdio: 'inherit',
});
```

Omit `shell: true` or set it to `false` explicitly.

## execa template literals

### Vulnerable

```typescript
const userPath: string = req.query.path as string;
const result = await execa(`find ${userPath} -type f`);
```

### Safe

```typescript
const userPath: string = req.query.path as string;
const result = await execa('find', [userPath, '-type', 'f']);
```

Pass command and arguments separately. Do not use template literals.

## Typed argument handling

When building arguments from request data, maintain type safety:

### Safe pattern

```typescript
const userInput: string = req.query.search as string;
if (!/^[a-zA-Z0-9 ]+$/.test(userInput)) {
    throw new Error("Invalid search term");
}
const args: string[] = [userInput, '/var/log/system.log'];
const result = await execa('grep', args);
```

Type-checking and validation work together to prevent injection.

## Refactoring to native APIs

The safest approach is to avoid shell execution:

### Before (using execa)

```typescript
import {execa} from 'execa';

const dir: string = req.query.directory as string;
const {stdout} = await execa('ls', [dir]);
const files = stdout.split('\n');
```

### After (using Node.js APIs)

```typescript
import {promises as fs} from 'fs';

const dir: string = req.query.directory as string;
const files = await fs.readdir(dir);
```

Use Node.js built-in APIs (fs, path, etc.) whenever possible.
