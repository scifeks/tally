# JavaScript prototype pollution patterns

Vulnerable-vs-safe snippets for Node.js libraries and patterns the
`injection.prototype_pollution` scanner recognizes. TypeScript-specific
patterns live in `typescript.md`.

## lodash merge

### Vulnerable

```javascript
const config = {};
const userSettings = req.body;
_.merge(config, userSettings);

const defaults = { role: "user" };
const userInput = req.query;
_.merge(defaults, userInput);
```

Older versions of lodash (before 4.17.21) do not filter `__proto__`
and `constructor.prototype` keys, allowing prototype pollution.

### Safe

```javascript
const config = {};
const userSettings = req.body;
if (userSettings && typeof userSettings === "object") {
  Object.keys(userSettings).forEach((key) => {
    if (!["__proto__", "constructor", "prototype"].includes(key)) {
      config[key] = userSettings[key];
    }
  });
}

const defaults = { role: "user" };
const userInput = req.query;
_.merge(defaults, userInput);
```

Upgrade lodash to 4.17.21 or later if not already there. If
upgrading is not an option, filter user input before merging. Never
merge untrusted data directly into a shared object.

## lodash set / defaultsDeep

### Vulnerable

```javascript
const user = {};
_.set(user, req.body.path, req.body.value);

const config = { debug: false, maxRetries: 3 };
_.defaultsDeep(config, req.query);
```

`_.set()` accepts a path like `"a.b.c"`, which can be `"__proto__.x"`
or `"constructor.prototype.x"`. `_.defaultsDeep()` is equivalent to
`_.merge()` and carries the same risk.

### Safe

```javascript
const user = {};
const pathParts = req.body.path.split(".");
if (!pathParts.some((p) => ["__proto__", "constructor"].includes(p))) {
  _.set(user, req.body.path, req.body.value);
}

const config = { debug: false, maxRetries: 3 };
const filtered = {};
Object.keys(req.query).forEach((key) => {
  if (!["__proto__", "constructor", "prototype"].includes(key)) {
    filtered[key] = req.query[key];
  }
});
_.defaultsDeep(config, filtered);
```

Validate the path or keys before calling `_.set()` or
`_.defaultsDeep()`.

## Custom recursive merge

### Vulnerable

```javascript
function mergeObjects(target, source) {
  for (const key in source) {
    if (typeof source[key] === "object" && source[key] !== null) {
      if (!(key in target)) {
        target[key] = {};
      }
      mergeObjects(target[key], source[key]);
    } else {
      target[key] = source[key];
    }
  }
  return target;
}

const defaults = { role: "user" };
const userConfig = req.body;
mergeObjects(defaults, userConfig);
```

The loop does not filter `__proto__`, `constructor`, or `prototype`,
allowing the attacker to modify the prototype chain of all objects.

### Safe

```javascript
function mergeObjects(target, source) {
  for (const key in source) {
    if (["__proto__", "constructor", "prototype"].includes(key)) {
      continue;
    }
    if (typeof source[key] === "object" && source[key] !== null) {
      if (!(key in target)) {
        target[key] = {};
      }
      mergeObjects(target[key], source[key]);
    } else {
      target[key] = source[key];
    }
  }
  return target;
}

const defaults = { role: "user" };
const userConfig = req.body;
mergeObjects(defaults, userConfig);
```

Filter dangerous keys at the start of each recursion level.

## Object.assign on shared state

### Vulnerable

```javascript
const sharedConfig = { timeout: 5000, debug: false };

app.post("/config", (req, res) => {
  Object.assign(sharedConfig, req.body);
  res.send("Updated");
});

app.get("/status", (req, res) => {
  res.json(sharedConfig);
});
```

If `req.body` contains `__proto__`, it can modify the prototype of
`sharedConfig` and affect all subsequent objects.

### Safe

```javascript
const sharedConfig = { timeout: 5000, debug: false };

app.post("/config", (req, res) => {
  const update = {};
  Object.keys(req.body).forEach((key) => {
    if (!["__proto__", "constructor", "prototype"].includes(key)) {
      update[key] = req.body[key];
    }
  });
  Object.assign(sharedConfig, update);
  res.send("Updated");
});

app.get("/status", (req, res) => {
  res.json(sharedConfig);
});
```

Validate input keys before calling `Object.assign()` on shared state.
Better, create a new object per request instead of mutating shared
state.

## Query string parsing (qs library)

### Vulnerable

```javascript
const qs = require("qs");

app.get("/search", (req, res) => {
  const params = qs.parse(req.querystring, { allowPrototypes: true });
  mergeIntoGlobalConfig(params);
  res.send("OK");
});
```

The `allowPrototypes: true` option permits parsing of `__proto__` and
`constructor` keys, enabling prototype pollution if the parsed object
is later merged into a shared state.

### Safe

```javascript
const qs = require("qs");

app.get("/search", (req, res) => {
  const params = qs.parse(req.querystring);
  res.send(params);
});
```

By default, `qs.parse()` disables prototype pollution parsing
(`allowPrototypes: false`). Never set `allowPrototypes: true` unless
you have a specific reason and validate keys afterward.

## JSON.parse and recursive merge

### Vulnerable

```javascript
app.post("/data", express.json(), (req, res) => {
  const defaults = { role: "user", permissions: [] };
  const userData = JSON.parse(JSON.stringify(req.body));
  mergeObjects(defaults, userData);
  storeUserInMemory(defaults);
  res.send("Stored");
});
```

Even though `JSON.parse` itself is safe, if the parsed result is then
merged into a shared or prototype-sensitive object without filtering,
prototype pollution can occur.

### Safe

```javascript
app.post("/data", express.json(), (req, res) => {
  const defaults = { role: "user", permissions: [] };
  const userData = req.body;
  const filtered = {};
  Object.keys(userData).forEach((key) => {
    if (!["__proto__", "constructor", "prototype"].includes(key)) {
      filtered[key] = userData[key];
    }
  });
  Object.assign(defaults, filtered);
  storeUserInMemory(defaults);
  res.send("Stored");
});
```

Filter user input before merging, regardless of where it came from.

## Deep clone libraries

### Vulnerable

```javascript
const deepclone = require("deepclone");

const config = { debug: false };
const userInput = req.body;
const merged = deepclone(config);
for (const key in userInput) {
  merged[key] = userInput[key];
}
```

If the deep clone library or the merge operation traverses
`__proto__`, the attacker can inject prototype pollution.

### Safe

```javascript
const config = { debug: false };
const userInput = req.body;
const merged = { ...config };
Object.keys(userInput).forEach((key) => {
  if (!["__proto__", "constructor", "prototype"].includes(key)) {
    merged[key] = userInput[key];
  }
});
```

Prefer shallow copies (`{...config}`) when possible. If deep cloning
is necessary, filter dangerous keys explicitly.

## Object.create(null) as target

### Safe

```javascript
const target = Object.create(null);
const userInput = req.body;
Object.assign(target, userInput);
const result = mergeObjects(target, userInput);
```

When the target has no prototype (`Object.create(null)`), there is no
prototype chain to pollute. This is the safest approach for
server-side processing of untrusted data.
