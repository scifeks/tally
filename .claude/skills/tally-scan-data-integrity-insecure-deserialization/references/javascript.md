# JavaScript insecure deserialization patterns

Vulnerable-vs-safe snippets for the JavaScript libraries the
`data_integrity.insecure_deserialization` scanner recognizes.

## node-serialize

### Vulnerable

```javascript
const serialize = require('node-serialize');

const data = req.body.payload;
const obj = serialize.unserialize(data);

const cached = req.query.state;
const state = serialize.unserialize(cached);
```

### Safe

```javascript
const data = req.body.payload;
const obj = JSON.parse(data);

const cached = req.query.state;
const state = JSON.parse(cached);
```

node-serialize allows IIFE (Immediately Invoked Function Expression) and
crafted payloads can execute arbitrary JavaScript. The library constructs
function objects from serialized code. Replace with JSON.parse() for all
data exchange and storage.

## serialize-to-js

### Vulnerable

```javascript
const ser = require('serialize-to-js');

const data = req.body.object;
const obj = ser.unserialize(data);
```

### Safe

```javascript
const data = req.body.object;
const obj = JSON.parse(data);
```

serialize-to-js is similar to node-serialize and allows code execution through
function objects in the serialized payload. Use JSON.parse() instead.

## js-yaml (v3 and earlier)

### Vulnerable

```javascript
const yaml = require('js-yaml');

const config = yaml.load(req.body.config);

const data = yaml.load(fs.readFileSync('user-config.yaml', 'utf8'));
```

### Safe (v3 with explicit SafeSchema)

```javascript
const yaml = require('js-yaml');

const config = yaml.load(req.body.config, { schema: yaml.SAFE_SCHEMA });

const data = yaml.load(fs.readFileSync('user-config.yaml', 'utf8'),
  { schema: yaml.SAFE_SCHEMA });
```

### Safe (v4+)

```javascript
const yaml = require('js-yaml');

const config = yaml.load(req.body.config);

const data = yaml.load(fs.readFileSync('user-config.yaml', 'utf8'));
```

In js-yaml v3, the default Loader accepts `!!js/function` tags that construct
function objects, which can execute code. Either upgrade to v4+ (which made
SafeSchema the default and removed js/function tag support) or explicitly set
`schema: yaml.SAFE_SCHEMA` in all load() calls.

## cryo

### Vulnerable

```javascript
const cryo = require('cryo');

const data = req.body.state;
const state = cryo.parse(data);
```

### Safe

```javascript
const data = req.body.state;
const state = JSON.parse(data);
```

cryo is a serialization library that preserves function objects. Do not use
on untrusted data. Use JSON.parse() instead.

## eval() of JSON-like strings

### Vulnerable

```javascript
const userConfig = req.body.config;
const config = eval('(' + userConfig + ')');

const data = req.query.filters;
const filters = eval(data);
```

### Safe

```javascript
const userConfig = req.body.config;
const config = JSON.parse(userConfig);

const data = req.query.filters;
const filters = JSON.parse(data);
```

`eval()` executes arbitrary JavaScript code. Use `JSON.parse()` for JSON
data or validate and parse the string against a schema.
