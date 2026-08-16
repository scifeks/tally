# TypeScript prototype pollution patterns

Vulnerable-vs-safe snippets for TypeScript-specific state management
and type-unsafe patterns the `injection.prototype_pollution` scanner
recognizes. Node.js-shared patterns (lodash, Object.assign, recursive
merge) live in `javascript.md`.

## Type-guarded merge with user input

### Vulnerable

```typescript
interface Config {
  debug: boolean;
  maxRetries: number;
  timeout: number;
}

function applySettings(defaults: Config, userInput: Partial<Config>): Config {
  return { ...defaults, ...userInput };
}

const config = applySettings(
  { debug: false, maxRetries: 3, timeout: 5000 },
  req.body as Partial<Config>
);
```

TypeScript's type system does not prevent `__proto__` or `constructor`
injection at runtime. The cast to `Partial<Config>` is a compile-time
check only; `req.body` can carry arbitrary keys.

### Safe

```typescript
interface Config {
  debug: boolean;
  maxRetries: number;
  timeout: number;
}

function applySettings(
  defaults: Config,
  userInput: Record<string, unknown>
): Config {
  const allowed = new Set(Object.keys(defaults));
  const filtered: Partial<Config> = {};
  for (const key in userInput) {
    if (allowed.has(key) && !["__proto__", "constructor"].includes(key)) {
      filtered[key as keyof Config] = userInput[key] as never;
    }
  }
  return { ...defaults, ...filtered };
}

const config = applySettings(
  { debug: false, maxRetries: 3, timeout: 5000 },
  req.body
);
```

Validate input keys against a known allowlist, independent of types.

## Redux store initialization

### Vulnerable

```typescript
import { createStore } from "redux";

const initialState: AppState = {
  user: { id: 0, role: "guest" },
  config: { debug: false },
};

function reducer(state = initialState, action: AnyAction): AppState {
  if (action.type === "APPLY_SETTINGS") {
    return {
      ...state,
      config: { ...state.config, ...action.payload },
    };
  }
  return state;
}

const store = createStore(reducer);

app.post("/apply", (req, res) => {
  store.dispatch({ type: "APPLY_SETTINGS", payload: req.body });
  res.send("Applied");
});
```

If `action.payload` contains `__proto__`, the spread operation can
pollute the store's prototype chain or the prototype of all subsequent
state objects.

### Safe

```typescript
import { createStore } from "redux";

const initialState: AppState = {
  user: { id: 0, role: "guest" },
  config: { debug: false },
};

const ALLOWED_CONFIG_KEYS = new Set(Object.keys(initialState.config));

function reducer(state = initialState, action: AnyAction): AppState {
  if (action.type === "APPLY_SETTINGS") {
    const filtered: Record<string, unknown> = {};
    for (const key in action.payload) {
      if (
        ALLOWED_CONFIG_KEYS.has(key) &&
        !["__proto__", "constructor", "prototype"].includes(key)
      ) {
        filtered[key] = action.payload[key];
      }
    }
    return {
      ...state,
      config: { ...state.config, ...filtered },
    };
  }
  return state;
}

const store = createStore(reducer);

app.post("/apply", (req, res) => {
  store.dispatch({ type: "APPLY_SETTINGS", payload: req.body });
  res.send("Applied");
});
```

Validate action payload keys in the reducer before applying updates.

## Vuex store mutation

### Vulnerable

```typescript
import { createStore } from "vuex";

const store = createStore({
  state() {
    return { config: { theme: "dark" } };
  },
  mutations: {
    updateConfig(state, payload: Partial<typeof state.config>) {
      Object.assign(state.config, payload);
    },
  },
});

export default store;
```

When `payload` comes from untrusted input and contains `__proto__` or
`constructor`, `Object.assign()` can pollute the prototype.

### Safe

```typescript
import { createStore } from "vuex";

const store = createStore({
  state() {
    return { config: { theme: "dark" } };
  },
  mutations: {
    updateConfig(
      state,
      payload: Record<string, unknown>
    ) {
      const allowed = new Set(Object.keys(state.config));
      for (const key in payload) {
        if (
          allowed.has(key) &&
          !["__proto__", "constructor", "prototype"].includes(key)
        ) {
          (state.config as Record<string, unknown>)[key] = payload[key];
        }
      }
    },
  },
});

export default store;
```

Validate mutation payload keys against a known set before mutating
state.

## Typed recursive merge

### Vulnerable

```typescript
interface UserSettings {
  language: string;
  theme: string;
  notifications: boolean;
}

function mergeSettings(
  defaults: UserSettings,
  userInput: UserSettings
): UserSettings {
  function merge(target: any, source: any): any {
    for (const key in source) {
      if (typeof source[key] === "object" && source[key] !== null) {
        if (!(key in target)) {
          target[key] = {};
        }
        merge(target[key], source[key]);
      } else {
        target[key] = source[key];
      }
    }
    return target;
  }
  return merge(defaults, userInput);
}

const settings = mergeSettings(
  { language: "en", theme: "light", notifications: true },
  req.body as UserSettings
);
```

The recursive function does not filter `__proto__`. TypeScript's type
annotation does not provide runtime safety.

### Safe

```typescript
interface UserSettings {
  language: string;
  theme: string;
  notifications: boolean;
}

const DANGEROUS_KEYS = new Set(["__proto__", "constructor", "prototype"]);

function mergeSettings(
  defaults: UserSettings,
  userInput: Partial<UserSettings>
): UserSettings {
  function merge(target: any, source: any): any {
    for (const key in source) {
      if (DANGEROUS_KEYS.has(key)) {
        continue;
      }
      if (typeof source[key] === "object" && source[key] !== null) {
        if (!(key in target)) {
          target[key] = {};
        }
        merge(target[key], source[key]);
      } else {
        target[key] = source[key];
      }
    }
    return target;
  }
  return merge({ ...defaults }, userInput);
}

const settings = mergeSettings(
  { language: "en", theme: "light", notifications: true },
  req.body as Partial<UserSettings>
);
```

Filter dangerous keys explicitly. Create a shallow copy of defaults
before merging to avoid modifying the original.

## NestJS controller with typed request body

### Vulnerable

```typescript
import { Body, Controller, Post } from "@nestjs/common";

interface SettingsDto {
  timeout: number;
  retries: number;
}

@Controller("config")
export class ConfigController {
  constructor(private configService: ConfigService) {}

  @Post("settings")
  async updateSettings(@Body() settings: SettingsDto): Promise<void> {
    const current = this.configService.get();
    Object.assign(current, settings);
    this.configService.set(current);
  }
}
```

NestJS validation decorators (`@IsNumber()`, etc.) check only known
fields. They do not strip `__proto__` or `constructor`. If the
underlying service merges settings into shared state, prototype
pollution can occur.

### Safe

```typescript
import { Body, Controller, Post } from "@nestjs/common";
import { IsNumber } from "class-validator";

class SettingsDto {
  @IsNumber()
  timeout!: number;

  @IsNumber()
  retries!: number;
}

@Controller("config")
export class ConfigController {
  constructor(private configService: ConfigService) {}

  @Post("settings")
  async updateSettings(@Body() settings: SettingsDto): Promise<void> {
    const current = this.configService.get();
    const update: Record<string, number> = {};
    if (typeof settings.timeout === "number") {
      update.timeout = settings.timeout;
    }
    if (typeof settings.retries === "number") {
      update.retries = settings.retries;
    }
    this.configService.set({ ...current, ...update });
  }
}
```

Explicitly extract known fields from the request body into a new
object, and merge that new object into the service state.

## Object.create(null) in TypeScript

### Safe

```typescript
interface Settings {
  debug: boolean;
  maxConnections: number;
}

function initializeSettings(userInput: Partial<Settings>): Settings {
  const target = Object.create(null) as Settings;
  const defaults: Settings = { debug: false, maxConnections: 10 };

  Object.assign(target, defaults);

  for (const key in userInput) {
    if (
      !["__proto__", "constructor", "prototype"].includes(key) &&
      key in defaults
    ) {
      (target as Record<string, any>)[key] = userInput[key as keyof Settings];
    }
  }

  return target;
}
```

Creating the target with `Object.create(null)` disables the prototype
chain entirely. This is the safest approach for processing untrusted
input, though the TypeScript casts are necessary.
