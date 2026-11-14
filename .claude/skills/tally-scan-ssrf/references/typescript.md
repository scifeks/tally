# TypeScript SSRF patterns

Safe and vulnerable code snippets for the TypeScript HTTP libraries and
frameworks the `ssrf` scanner recognizes. When multiple safe forms
exist, the canonical one is shown first.

## NestJS HttpService

### Vulnerable

```typescript
import { HttpService } from "@nestjs/axios";
import { Injectable } from "@nestjs/common";

@Injectable()
export class WebhookService {
  constructor(private httpService: HttpService) {}

  async triggerWebhook(url: string): Promise<any> {
    return this.httpService.get(url).toPromise();
  }
}

async handleCallback(dto: { url: string }): Promise<void> {
  await this.httpService.post(dto.url, {}).toPromise();
}
```

### Safe

```typescript
import { HttpService } from "@nestjs/axios";
import { Injectable, BadRequestException } from "@nestjs/common";

@Injectable()
export class UrlValidator {
  private allowedDomains = ["api.example.com", "webhook.service.io"];

  validate(urlString: string): void {
    const parsed = new URL(urlString);
    if (!this.allowedDomains.includes(parsed.hostname)) {
      throw new BadRequestException("Domain not allowlisted");
    }
    if (parsed.protocol === "file:") {
      throw new BadRequestException("file: protocol not allowed");
    }
  }
}

@Injectable()
export class WebhookService {
  constructor(
    private httpService: HttpService,
    private validator: UrlValidator
  ) {}

  async triggerWebhook(url: string): Promise<any> {
    this.validator.validate(url);
    return this.httpService.get(url).toPromise();
  }
}
```

## axios with TypeScript

### Vulnerable

```typescript
import axios from "axios";

async function fetchData(url: string): Promise<void> {
  const response = await axios.get(url);
  console.log(response.data);
}

async function postToWebhook(dto: {
  callback_url: string;
}): Promise<void> {
  await axios.post(dto.callback_url, { status: "done" });
}
```

### Safe

```typescript
import axios from "axios";

const ALLOWED_DOMAINS = ["api.example.com", "webhook.service.io"];

function validateUrl(urlString: string): void {
  const parsed = new URL(urlString);
  if (!ALLOWED_DOMAINS.includes(parsed.hostname)) {
    throw new Error("Domain not allowlisted");
  }
}

async function fetchData(url: string): Promise<void> {
  validateUrl(url);
  const response = await axios.get(url);
  console.log(response.data);
}
```

## fetch API (TypeScript)

### Vulnerable

```typescript
async function downloadImage(url: string): Promise<Buffer> {
  const response = await fetch(url);
  return response.arrayBuffer() as Promise<Buffer>;
}

async function callWebhook(config: { webhookUrl: string }): Promise<void> {
  await fetch(config.webhookUrl, {
    method: "POST",
    body: JSON.stringify({ event: "processed" })
  });
}
```

### Safe

```typescript
const TRUSTED_HOSTS = ["cdn.example.com", "api.example.com"];

function validateUrl(urlString: string): void {
  const parsed = new URL(urlString);
  if (!TRUSTED_HOSTS.includes(parsed.hostname)) {
    throw new Error("Host not in allowlist");
  }
}

async function downloadImage(url: string): Promise<Buffer> {
  validateUrl(url);
  const response = await fetch(url);
  return response.arrayBuffer() as Promise<Buffer>;
}
```

## undici

### Vulnerable

```typescript
import { fetch } from "undici";

async function makeRequest(userUrl: string): Promise<void> {
  const response = await fetch(userUrl);
  console.log(response.status);
}
```

### Safe

```typescript
import { fetch } from "undici";

const ALLOWED_DOMAINS = ["api.example.com"];

function validateUrl(urlString: string): void {
  const parsed = new URL(urlString);
  if (!ALLOWED_DOMAINS.includes(parsed.hostname)) {
    throw new Error("Domain not allowlisted");
  }
}

async function makeRequest(userUrl: string): Promise<void> {
  validateUrl(userUrl);
  const response = await fetch(userUrl);
  console.log(response.status);
}
```

## Validation helper (reusable)

A utility function you can inject into services:

```typescript
export interface UrlValidationConfig {
  allowedDomains: string[];
  blockPrivateIps?: boolean;
}

export class UrlValidator {
  private config: UrlValidationConfig;

  constructor(config: UrlValidationConfig) {
    this.config = config;
  }

  validate(urlString: string): void {
    const parsed = new URL(urlString);

    if (!this.config.allowedDomains.includes(parsed.hostname)) {
      throw new Error(`Domain ${parsed.hostname} not allowlisted`);
    }

    if (this.config.blockPrivateIps) {
      this.checkPrivateIp(parsed.hostname);
    }
  }

  private checkPrivateIp(hostname: string): void {
    const privatePatterns = [
      /^127\./,
      /^10\./,
      /^172\.(1[6-9]|2[0-9]|3[01])\./,
      /^192\.168\./
    ];
    if (privatePatterns.some(p => p.test(hostname))) {
      throw new Error("Private IP ranges not allowed");
    }
  }
}
```

Usage in a NestJS service:

```typescript
const validator = new UrlValidator({
  allowedDomains: ["api.example.com"],
  blockPrivateIps: true
});

validator.validate(userProvidedUrl);
await axios.get(userProvidedUrl);
```
