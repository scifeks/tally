# JavaScript OS command injection patterns

Vulnerable-vs-safe snippets for the Node.js child_process patterns the
`injection.os_command` scanner recognizes. When multiple safe forms exist,
the canonical one is shown first.

## child_process.exec()

### Vulnerable

```javascript
const userInput = req.query.command;
exec(`ls ${userInput}`, (error, stdout, stderr) => {
    console.log(stdout);
});

const dir = req.body.directory;
exec("grep " + searchTerm + " " + dir, (error, stdout) => {
    // ...
});
```

### Safe

```javascript
const userInput = req.query.command;
execFile("ls", [userInput], (error, stdout, stderr) => {
    console.log(stdout);
});
```

Never use `exec()` with user input. Use `execFile()` with argument arrays
instead.

## child_process.execSync()

### Vulnerable

```javascript
const userInput = req.query.filename;
const output = execSync(`cat ${userInput}`, {encoding: 'utf-8'});
```

### Safe

```javascript
const userInput = req.query.filename;
const output = execFileSync("cat", [userInput], {encoding: 'utf-8'});
```

Use `execFileSync()` with argument arrays. Never use `execSync()` with
template literals or string concatenation.

## child_process.spawn() with shell

### Vulnerable

```javascript
const userDir = req.query.dir;
const child = spawn('sh', ['-c', `ls ${userDir}`]);

const proc = spawn('/bin/bash', ['-c', 'grep ' + searchTerm]);
```

### Safe

```javascript
const userDir = req.query.dir;
const child = spawn('ls', [userDir]);

const proc = spawn('grep', [searchTerm], {
    stdio: 'inherit',
});
```

Do not use `spawn('sh', ['-c', ...])` with user input. Pass command and
arguments separately.

## child_process.execFile()

### Safe (baseline for comparison)

```javascript
const userInput = req.query.pattern;
execFile('grep', [userInput, '/var/log/access.log'], (err, stdout) => {
    console.log(stdout);
});
```

`execFile()` does not invoke a shell. Arguments are passed directly to the
executable, so shell metacharacters are not interpreted. This is the safe
pattern.

## child_process.fork()

### Safe (baseline for comparison)

```javascript
const worker = fork('./worker.js');
worker.send({input: userInput});
```

`fork()` spawns a new Node.js process without invoking the shell. Safe for
inter-process communication.

## Quoting user input in exec()

If you must use `exec()` (not recommended), quote each argument:

### Suboptimal

```javascript
const userInput = req.query.name;
const {execSync} = require('child_process');
const shlex = require('shellquote');
const safeInput = shlex.quote([userInput])[0];
exec(`echo ${safeInput}`, (error, stdout) => {
    console.log(stdout);
});
```

This is a fallback only. `execFile()` is safer and does not require a
quoting library.

## Refactoring to built-in APIs

The safest approach is to avoid shell execution entirely:

### Before (using shell)

```javascript
const dir = req.query.directory;
const files = execSync(`ls ${dir}`).toString().split('\n');
```

### After (using Node.js APIs)

```javascript
const dir = req.query.directory;
const files = fs.readdirSync(dir);
```

Use Node.js built-in APIs (fs, path, etc.) whenever possible.
