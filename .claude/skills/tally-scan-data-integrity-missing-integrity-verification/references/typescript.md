# TypeScript data integrity verification patterns

Vulnerable-vs-safe snippets for the TypeScript HTTP, webhook, JWT, and
NestJS patterns the `data_integrity.missing_integrity_verification` scanner
recognizes. TypeScript patterns mirror JavaScript with added type safety.

## typed fetch: HTTP artifact download

### Vulnerable

```typescript
interface PluginConfig {
  name: string;
  version: string;
}

const response = await fetch("https://trusted-domain.com/plugin.json");
const config: PluginConfig = await response.json();
applyConfig(config);
```

### Safe

```typescript
import * as crypto from "crypto";

interface PluginConfig {
  name: string;
  version: string;
}

const response = await fetch("https://trusted-domain.com/plugin.json");
const content = await response.text();
const expectedHash: string = "abc123def456...";
const actualHash: string = crypto
  .createHash("sha256")
  .update(content)
  .digest("hex");
if (actualHash !== expectedHash) {
  throw new Error("Hash mismatch");
}
const config: PluginConfig = JSON.parse(content);
applyConfig(config);
```

Always verify the hash of downloaded JSON content before parsing and using
it. Capture the raw response text to compute the hash.

## axios with TypeScript: HTTP artifact download

### Vulnerable

```typescript
import axios from "axios";

interface DataPayload {
  orders: Array<{id: number; amount: number}>;
}

const response = await axios.get<DataPayload>(
  "https://trusted-domain.com/orders.json"
);
processOrders(response.data.orders);
```

### Safe

```typescript
import axios from "axios";
import * as crypto from "crypto";

interface DataPayload {
  orders: Array<{id: number; amount: number}>;
}

const response = await axios.get<string>(
  "https://trusted-domain.com/orders.json",
  {responseType: "text"}
);
const expectedHash: string = "def789ghi012...";
const actualHash: string = crypto
  .createHash("sha256")
  .update(response.data)
  .digest("hex");
if (actualHash !== expectedHash) {
  throw new Error("Hash mismatch");
}
const data: DataPayload = JSON.parse(response.data);
processOrders(data.orders);
```

Request the response as raw text (`responseType: "text"`), verify the hash,
then parse the JSON.

## Express with TypeScript: Webhook signature verification

### Vulnerable

```typescript
import express from "express";

interface Order {
  id: string;
  amount: number;
}

app.post("/webhook", express.json(), (req: express.Request, res: express.Response) => {
  const order: Order = req.body;
  processOrder(order);
  res.json({status: "ok"});
});
```

### Safe

```typescript
import express from "express";
import * as crypto from "crypto";

interface Order {
  id: string;
  amount: number;
}

const verifyWebhookSignature = (
  req: express.Request,
  res: express.Response,
  next: express.NextFunction
): void => {
  const signature: string | undefined =
    req.headers["x-hub-signature-256"] as string | undefined;
  if (!signature) {
    res.status(401).json({error: "Missing signature"});
    return;
  }
  const secret: string = process.env.WEBHOOK_SECRET || "";
  const expected: string = "sha256=" + crypto
    .createHmac("sha256", secret)
    .update(req.rawBody || "")
    .digest("hex");
  if (!crypto.timingSafeEqual(
    Buffer.from(expected),
    Buffer.from(signature)
  )) {
    res.status(401).json({error: "Invalid signature"});
    return;
  }
  next();
};

app.use(express.raw({type: "application/json"}));
app.post(
  "/webhook",
  verifyWebhookSignature,
  (req: express.Request, res: express.Response) => {
  const order: Order = JSON.parse((req.rawBody || "").toString());
  processOrder(order);
  res.json({status: "ok"});
});
```

Use type annotations on request and response objects. Verify the HMAC
signature using the raw body buffer before parsing JSON.

## NestJS guard: Webhook signature verification

### Vulnerable

```typescript
import {Injectable, CanActivate, ExecutionContext} from "@nestjs/common";
import {Request} from "express";

@Injectable()
export class WebhookGuard implements CanActivate {
  canActivate(context: ExecutionContext): boolean {
    const request: Request = context.switchToHttp().getRequest();
    const signature: string | undefined =
      request.headers["x-hub-signature-256"] as
        string | undefined;
    return signature !== undefined;
  }
}

@Controller("/webhook")
export class WebhookController {
  @Post()
  @UseGuards(WebhookGuard)
  handleWebhook(@Body() data: Order): object {
    processOrder(data);
    return {status: "ok"};
  }
}
```

### Safe

```typescript
import {Injectable, CanActivate, ExecutionContext} from "@nestjs/common";
import {Request} from "express";
import * as crypto from "crypto";

@Injectable()
export class WebhookGuard implements CanActivate {
  canActivate(context: ExecutionContext): boolean {
    const request: Request = context.switchToHttp().getRequest();
    const signature: string | undefined =
      request.headers["x-hub-signature-256"] as
        string | undefined;
    if (!signature) {
      return false;
    }
    const secret: string = process.env.WEBHOOK_SECRET || "";
    const rawBody: Buffer = (request as any).rawBody || Buffer.alloc(0);
    const expected: string = "sha256=" + crypto
      .createHmac("sha256", secret)
      .update(rawBody)
      .digest("hex");
    return crypto.timingSafeEqual(
      Buffer.from(expected),
      Buffer.from(signature)
    );
  }
}

@Controller("/webhook")
export class WebhookController {
  @Post()
  @UseGuards(WebhookGuard)
  handleWebhook(@Body() data: Order): object {
    processOrder(data);
    return {status: "ok"};
  }
}
```

Always verify the HMAC in the guard before the route handler executes.
Use the raw request body, not the parsed JSON. Use `crypto.timingSafeEqual()`
for comparison.

## jsonwebtoken with TypeScript: JWT verification

### Vulnerable

```typescript
import jwt from "jsonwebtoken";
import {Request, Response} from "express";

interface JwtPayload {
  user_id: string;
  email: string;
}

app.get("/profile", (req: Request, res: Response) => {
  const token: string = req.headers.authorization?.replace("Bearer ", "") || "";
  const payload: any = jwt.decode(token);
  const userId: string = payload.user_id;
  res.json({userId});
});
```

### Safe

```typescript
import jwt from "jsonwebtoken";
import {Request, Response} from "express";

interface JwtPayload {
  user_id: string;
  email: string;
}

app.get("/profile", (req: Request, res: Response) => {
  const token: string = req.headers.authorization?.replace("Bearer ", "") || "";
  const secret: string = process.env.JWT_SECRET || "";
  try {
    const payload: JwtPayload = jwt.verify(
      token,
      secret,
      {algorithms: ["HS256"]}
    ) as JwtPayload;
    const userId: string = payload.user_id;
    res.json({userId});
  } catch (err) {
    res.status(401).json({error: "Invalid token"});
  }
});
```

Always use `jwt.verify()` with an explicit `algorithms` array. Use type
casting to the payload interface for type safety. Never allow `"none"` in
the algorithms list.

## jose: JWT verification with TypeScript

### Vulnerable

```typescript
import * as jose from "jose";

interface Claims {
  sub: string;
  role: string;
}

export async function verifyToken(token: string): Promise<Claims> {
  const {payload} = await jose.jwtVerify(token, new TextEncoder().encode(""));
  return payload as Claims;
}
```

### Safe

```typescript
import * as jose from "jose";

interface Claims {
  sub: string;
  role: string;
}

const secret: string = process.env.JWT_SECRET || "";

export async function verifyToken(token: string): Promise<Claims> {
  try {
    const {payload} = await jose.jwtVerify(
      token,
      new TextEncoder().encode(secret),
      {algorithms: ["HS256"]}
    );
    return payload as Claims;
  } catch (err) {
    throw new Error("Invalid token");
  }
}
```

Always pass a secret and specify the `algorithms` option. Never pass an
empty string or omit algorithm validation.

## Dynamic module import with integrity verification

### Vulnerable

```typescript
import * as fs from "fs";
import {Request, Response} from "express";

interface Plugin {
  init(): void;
}

app.get("/load-plugin", async (req: Request, res: Response) => {
  const pluginName: string = req.query.plugin as string;
  const pluginPath: string = `./plugins/${pluginName}.js`;
  const plugin: Plugin = await import(pluginPath);
  plugin.init();
  res.json({status: "loaded"});
});
```

### Safe

```typescript
import * as fs from "fs";
import * as crypto from "crypto";
import {Request, Response} from "express";

interface PluginConfig {
  path: string;
  hash: string;
}

interface Plugin {
  init(): void;
}

const allowedPlugins: Record<string, PluginConfig> = {
  "plugin_v1": {
    path: "./plugins/plugin_v1.js",
    hash: "abc123def456..."
  },
  "plugin_v2": {
    path: "./plugins/plugin_v2.js",
    hash: "def789ghi012..."
  }
};

app.get("/load-plugin", async (req: Request, res: Response) => {
  const pluginName: string = req.query.plugin as string;
  const config: PluginConfig | undefined = allowedPlugins[pluginName];
  if (!config) {
    res.status(400).json({error: "Unknown plugin"});
    return;
  }
  const content: string = fs.readFileSync(config.path, "utf8");
  const actualHash: string = crypto
    .createHash("sha256")
    .update(content)
    .digest("hex");
  if (actualHash !== config.hash) {
    throw new Error("Hash mismatch");
  }
  const plugin: Plugin = await import(config.path);
  plugin.init();
  res.json({status: "loaded"});
});
```

Maintain a typed allowlist of known-good plugins and their hashes. Verify
the file hash before importing.
