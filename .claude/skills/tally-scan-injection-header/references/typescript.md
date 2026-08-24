# TypeScript HTTP header injection patterns

Vulnerable-vs-safe snippets for TypeScript web frameworks. TypeScript
compiles to JavaScript and runs on Node.js; the runtime behavior is
identical to JavaScript. These examples show type-safe patterns used in
typed Express, Fastify, and similar frameworks.

## Express with TypeScript

### Vulnerable

```typescript
import { Request, Response } from "express";

app.get("/redirect", (req: Request, res: Response) => {
  const url: string = req.query.goto as string;
  res.setHeader("Location", url);
  res.sendStatus(302);
});
```

### Safe

```typescript
import { Request, Response } from "express";

const ALLOWED_DOMAINS: string[] = ["example.com", "trusted.com"];

app.get("/redirect", (req: Request, res: Response) => {
  const goto = req.query.goto as string | undefined;
  if (!goto) {
    res.setHeader("Location", "/");
    res.sendStatus(302);
    return;
  }

  try {
    const parsed = new URL(goto);
    if (
      ["http:", "https:"].includes(parsed.protocol) &&
      ALLOWED_DOMAINS.includes(parsed.hostname)
    ) {
      res.setHeader("Location", goto);
    } else {
      res.setHeader("Location", "/");
    }
  } catch {
    res.setHeader("Location", "/");
  }
  res.sendStatus(302);
});
```

Validate all user-supplied URLs before setting the Location header.

## Fastify with TypeScript

### Vulnerable

```typescript
import { FastifyRequest, FastifyReply } from "fastify";

fastify.get("/download", async (request: FastifyRequest, reply: FastifyReply) => {
  const filename: string = request.query.file as string;
  reply.header("Content-Disposition", `attachment; filename=${filename}`);
  reply.send(data);
});
```

### Safe

```typescript
import { FastifyRequest, FastifyReply } from "fastify";

fastify.get("/download", async (request: FastifyRequest, reply: FastifyReply) => {
  let filename: string = (request.query.file as string) || "download.bin";
  filename = filename.replace(/[^a-zA-Z0-9._-]/g, "");
  if (!filename) {
    filename = "download.bin";
  }
  reply.header("Content-Disposition", `attachment; filename="${filename}"`);
  reply.send(data);
});
```

Sanitize filenames to allow only safe characters. Avoid placing user input
directly in headers.

## URL validation helper

Create a reusable typed helper:

```typescript
interface ValidateUrlResult {
  isValid: boolean;
  url: string;
}

function validateRedirectUrl(
  url: string | undefined,
  allowedDomains: string[]
): ValidateUrlResult {
  if (!url) {
    return { isValid: false, url: "/" };
  }

  try {
    const parsed = new URL(url);
    if (
      ["http:", "https:"].includes(parsed.protocol) &&
      allowedDomains.includes(parsed.hostname)
    ) {
      return { isValid: true, url };
    }
  } catch {
    // Invalid URL
  }

  return { isValid: false, url: "/" };
}

app.get("/redirect", (req: Request, res: Response) => {
  const { url } = validateRedirectUrl(
    req.query.goto as string,
    ALLOWED_DOMAINS
  );
  res.redirect(url);
});
```

Type-safe validation helpers make it easier to apply the same checks
across multiple endpoints.

## Generic header-value filtering pattern

If you must accept user input in a header, filter it:

```typescript
function safeHeaderValue(value: string | undefined): string {
  return String(value || "").replace(/[\r\n]/g, "");
}

const custom = req.query.x_custom as string | undefined;
res.setHeader("X-Custom", safeHeaderValue(custom));
```

This is a fallback when validation is not possible. Prefer allowlist
validation or built-in framework helpers.

## Important runtime note

TypeScript compiles to JavaScript and runs on Node.js. The runtime
behavior is identical to JavaScript code. Type-checking at compile time
does not prevent injection—it only validates the type (e.g., that a value
is a `string`). Runtime validation of user input is mandatory.
