# JavaScript path traversal patterns

Vulnerable-vs-safe snippets for the JavaScript (Node.js) file
operations the `access_control.path_traversal` scanner recognizes.
When multiple safe forms exist, the canonical one is shown first.

## fs.readFile / fs.readFileSync

### Vulnerable

```javascript
const filename = req.query.file;
fs.readFile(
    path.join(__dirname, 'uploads', filename),
    (err, data) => {
        if (err) return res.status(500).send(err);
        res.send(data);
    }
);

fs.readFile(
    path.join('/var/data', req.params.filename),
    'utf8',
    (err, data) => {
        res.json({ content: data });
    }
);
```

### Safe

```javascript
const path = require('path');
const filename = req.query.file;
const baseDir = path.resolve(__dirname, 'uploads');
const filepath = path.resolve(baseDir, filename);
if (!filepath.startsWith(baseDir + path.sep)) {
    return res.status(403).send('Access denied');
}
fs.readFile(filepath, (err, data) => {
    if (err) return res.status(500).send(err);
    res.send(data);
});

// or use path.basename to strip directories
const filename = path.basename(req.query.file);
fs.readFile(
    path.join(__dirname, 'uploads', filename),
    (err, data) => {
        if (err) return res.status(500).send(err);
        res.send(data);
    }
);
```

Always use `path.resolve()` to normalize the path and verify it starts
with the base directory. Or use `path.basename()` to strip directory
components from the user input.

## fs.createReadStream

### Vulnerable

```javascript
const file = req.params.file;
const stream = fs.createReadStream(
    path.join('/data', file)
);
res.setHeader('Content-Type', 'application/octet-stream');
stream.pipe(res);
```

### Safe

```javascript
const file = req.params.file;
const baseDir = path.resolve('/data');
const filepath = path.resolve(baseDir, file);
if (!filepath.startsWith(baseDir + path.sep)) {
    return res.status(403).send('Access denied');
}
const stream = fs.createReadStream(filepath);
res.setHeader('Content-Type', 'application/octet-stream');
stream.pipe(res);
```

Validate the resolved path before creating the stream.

## fs.writeFile / fs.writeFileSync

### Vulnerable

```javascript
const filename = req.body.filename;
const data = req.body.content;
fs.writeFile(
    path.join('/uploads', filename),
    data,
    (err) => {
        if (err) return res.status(500).send(err);
        res.send('File saved');
    }
);
```

### Safe

```javascript
const filename = path.basename(req.body.filename);
const baseDir = path.resolve('/uploads');
const filepath = path.resolve(baseDir, filename);
if (!filepath.startsWith(baseDir + path.sep)) {
    return res.status(403).send('Access denied');
}
fs.writeFile(filepath, req.body.content, (err) => {
    if (err) return res.status(500).send(err);
    res.send('File saved');
});
```

Use `path.basename()` to strip directory components, or validate the
resolved path stays within the base directory.

## res.sendFile / res.download

### Vulnerable

```javascript
const file = req.params.file;
res.sendFile(path.join(__dirname, 'static', file));

res.download(
    path.join('/exports', req.query.document)
);
```

### Safe

```javascript
const file = req.params.file;
const baseDir = path.resolve(__dirname, 'static');
const filepath = path.resolve(baseDir, file);
if (!filepath.startsWith(baseDir + path.sep)) {
    return res.status(403).send('Access denied');
}
res.sendFile(filepath);

// or
const document = path.basename(req.query.document);
res.download(path.join('/exports', document));
```

Validate containment before calling `sendFile` or `download`.

## fs.stat / fs.lstat / fs.access

### Vulnerable

```javascript
const file = req.query.file;
fs.stat(path.join('/var/www', file), (err, stats) => {
    if (!err && stats.isFile()) {
        res.json({ size: stats.size });
    }
});
```

### Safe

```javascript
const file = req.query.file;
const baseDir = path.resolve('/var/www');
const filepath = path.resolve(baseDir, file);
if (!filepath.startsWith(baseDir + path.sep)) {
    return res.status(403).send('Access denied');
}
fs.stat(filepath, (err, stats) => {
    if (!err && stats.isFile()) {
        res.json({ size: stats.size });
    }
});
```

Validate the path before stat, lstat, or access calls.

## String concatenation patterns

### Vulnerable

```javascript
const baseDir = '/data';
const file = req.params.file;
const filepath = baseDir + '/' + file;
fs.readFile(filepath, (err, data) => {
    res.send(data);
});
```

### Safe

```javascript
const baseDir = path.resolve('/data');
const file = req.params.file;
const filepath = path.resolve(baseDir, file);
if (!filepath.startsWith(baseDir + path.sep)) {
    return res.status(403).send('Access denied');
}
fs.readFile(filepath, (err, data) => {
    res.send(data);
});
```

Never concatenate strings into file paths. Always use `path.resolve()`
and validate containment.
