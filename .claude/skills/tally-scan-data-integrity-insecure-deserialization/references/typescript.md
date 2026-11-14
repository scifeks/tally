# TypeScript insecure deserialization patterns

Vulnerable-vs-safe snippets for the TypeScript libraries the
`data_integrity.insecure_deserialization` scanner recognizes. TypeScript
wraps the JavaScript runtime; the same unsafe libraries and patterns apply.

## js-yaml with TypeScript

### Vulnerable

```typescript
import * as yaml from 'js-yaml';

const config: Config = yaml.load(req.body.config);

const data: UserSettings = yaml.load(fs.readFileSync(
  userConfigPath, 'utf8'
));
```

### Safe (v3 with explicit SafeSchema)

```typescript
import * as yaml from 'js-yaml';

const config: Config = yaml.load(req.body.config, {
  schema: yaml.SAFE_SCHEMA,
});

const data: UserSettings = yaml.load(fs.readFileSync(
  userConfigPath, 'utf8'
), { schema: yaml.SAFE_SCHEMA });
```

### Safe (v4+)

```typescript
import * as yaml from 'js-yaml';

const config: Config = yaml.load(req.body.config);

const data: UserSettings = yaml.load(fs.readFileSync(
  userConfigPath, 'utf8'
));
```

In js-yaml v3, the default Loader accepts `!!js/function` tags. Either
upgrade to v4+ or explicitly set `schema: yaml.SAFE_SCHEMA`.

## class-transformer with untrusted input

### Vulnerable

```typescript
import { plainToInstance } from 'class-transformer';

class UserDTO {
  @Type(() => ChildClass)
  child: ChildClass;
}

class ChildClass {
  constructor(public value: string) {}
}

const user = plainToInstance(UserDTO, req.body.data, {
  enableImplicitConversion: true,
});
```

### Safe

```typescript
import { plainToInstance } from 'class-transformer';
import { validate } from 'class-validator';

class UserDTO {
  @Type(() => ChildClass)
  @IsString()
  child: string;
}

const user = plainToInstance(UserDTO, req.body.data, {
  enableImplicitConversion: false,
});
await validate(user);
```

class-transformer's `@Type()` decorator instantiates classes during
transformation. When `enableImplicitConversion` is true and the target class
has type-decorated properties, untrusted input can trigger object
instantiation with attacker-controlled property values. Set
`enableImplicitConversion: false` and validate the result against a
schema (class-validator).

## node-serialize and serialize-to-js

### Vulnerable

```typescript
import * as ser from 'node-serialize';

const data: string = req.body.payload;
const obj = ser.unserialize(data);
```

### Safe

```typescript
const data: string = req.body.payload;
const obj = JSON.parse(data);
```

See the JavaScript reference for details. Replace with JSON.parse().

## eval() in TypeScript

### Vulnerable

```typescript
const userConfig: string = req.body.config;
const config: Config = eval('(' + userConfig + ')');
```

### Safe

```typescript
const userConfig: string = req.body.config;
const config: Config = JSON.parse(userConfig);
```

Never use `eval()`. Use `JSON.parse()` for JSON data or validate against a
schema.
