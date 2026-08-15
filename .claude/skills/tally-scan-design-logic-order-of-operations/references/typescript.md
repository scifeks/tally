# TypeScript order-of-operations patterns

Vulnerable-vs-safe snippets for TypeScript frameworks that the
`design_logic.order_of_operations` scanner recognizes.

## NestJS guard ordering

### Vulnerable

```typescript
import { Controller, Get, UseGuards } from '@nestjs/common';
import { AuthzGuard } from './authz.guard';
import { AuthnGuard } from './authn.guard';

@Controller('/admin')
export class AdminController {
  @Get('/dashboard')
  @UseGuards(AuthzGuard, AuthnGuard)
  async getDashboard() {
    return { message: 'Admin dashboard' };
  }
}
```

NestJS executes guards left-to-right. `AuthzGuard` runs before
`AuthnGuard`. An unauthenticated user reaches the authorization guard.

### Safe

```typescript
@Controller('/admin')
export class AdminController {
  @Get('/dashboard')
  @UseGuards(AuthnGuard, AuthzGuard)
  async getDashboard() {
    return { message: 'Admin dashboard' };
  }
}
```

Guards execute left-to-right: `AuthnGuard` first, then `AuthzGuard`.
The user is authenticated before permission is checked.

## NestJS pipe and controller interaction

### Vulnerable

```typescript
@Post('/users')
async createUser(@Body() body: any) {
  const email = body.email;
  if (!isValidEmail(email)) {
    throw new BadRequestException('Invalid email');
  }
  const user = await this.userService.create(body);
  return user;
}
```

The controller method accesses `body.email` before validation runs.
Unvalidated data is used.

### Safe (with ValidationPipe)

```typescript
@Post('/users')
async createUser(@Body(ValidationPipe) createUserDto: CreateUserDto) {
  const user = await this.userService.create(createUserDto);
  return user;
}
```

The `ValidationPipe` decorator validates the request body before the
controller method runs. NestJS enforces the order.

Alternatively, validate explicitly before use:

```typescript
@Post('/users')
async createUser(@Body() body: any) {
  const schema = z.object({
    email: z.string().email(),
  });
  const validated = schema.parse(body);
  const user = await this.userService.create(validated);
  return user;
}
```

## Zod validation before persistence

### Vulnerable

```typescript
const userSchema = z.object({
  email: z.string().email(),
  name: z.string(),
});

async function createUser(data: unknown) {
  const user = new User({
    email: data.email,
    name: data.name,
  });
  await user.save();
  
  const validated = userSchema.parse(data);
  return validated;
}
```

The user is saved before validation. Invalid data reaches the database.

### Safe

```typescript
async function createUser(data: unknown) {
  const validated = userSchema.parse(data);
  
  const user = new User(validated);
  await user.save();
  
  return validated;
}
```

Validation runs before persistence. Only valid data is saved.

## Prisma type narrowing

### Vulnerable

```typescript
async function updateUser(id: string, data: any) {
  const updated = await prisma.user.update({
    where: { id },
    data: data,
  });
  
  const schema = z.object({
    email: z.string().email(),
  });
  
  const validated = schema.parse(data);
  return updated;
}
```

The update runs before validation. Unvalidated data reaches the
database.

### Safe

```typescript
async function updateUser(id: string, data: any) {
  const schema = z.object({
    email: z.string().email().optional(),
    name: z.string().optional(),
  });
  
  const validated = schema.parse(data);
  
  const updated = await prisma.user.update({
    where: { id },
    data: validated,
  });
  
  return updated;
}
```

Validation runs before the database operation. Only valid data reaches
the database.

## Express typed middleware

### Vulnerable

```typescript
app.use((req: Request, res: Response, next: NextFunction) => {
  if (!req.user?.role?.includes('admin')) {
    res.status(403).json({ error: 'Forbidden' });
  } else {
    next();
  }
});

app.use((req: Request, res: Response, next: NextFunction) => {
  req.user = await authenticate(req);
  next();
});
```

Middleware executes in registration order. Authorization runs before
authentication. An unauthenticated user bypasses the role check.

### Safe

```typescript
app.use(async (req: Request, res: Response, next: NextFunction) => {
  req.user = await authenticate(req);
  next();
});

app.use((req: Request, res: Response, next: NextFunction) => {
  if (!req.user?.role?.includes('admin')) {
    res.status(403).json({ error: 'Forbidden' });
  } else {
    next();
  }
});
```

Middleware executes in order: authentication first, then authorization.

## Fastify TypeScript hook ordering

### Vulnerable

```typescript
fastify.addHook('preHandler', async (request, reply) => {
  const user = request.user;
  if (!user || !user.roles.includes('admin')) {
    reply.code(403).send({ error: 'Forbidden' });
  }
});

fastify.addHook('onRequest', async (request, reply) => {
  request.user = await authenticate(request);
});
```

Fastify executes `onRequest` hooks first, then `preHandler` hooks.
Authorization runs before authentication is set. An unauthenticated
request bypasses the role check.

### Safe

```typescript
fastify.addHook('onRequest', async (request, reply) => {
  request.user = await authenticate(request);
});

fastify.addHook('preHandler', async (request, reply) => {
  const user = request.user;
  if (!user || !user.roles.includes('admin')) {
    reply.code(403).send({ error: 'Forbidden' });
  }
});
```

Hooks execute in documented order: `onRequest` first (authentication),
then `preHandler` (authorization).

## Class-validator with controller

### Vulnerable

```typescript
import { IsEmail, IsString } from 'class-validator';

class CreateUserDto {
  @IsEmail()
  email: string;

  @IsString()
  name: string;
}

@Post('/users')
async createUser(@Body() createUserDto: CreateUserDto) {
  const user = new User(createUserDto);
  await user.save();
  return user;
}
```

Without the `ValidationPipe`, the `@IsEmail()` and `@IsString()`
decorators do nothing. Unvalidated data reaches the database.

### Safe

```typescript
@Post('/users')
async createUser(
  @Body(new ValidationPipe({ transform: true, whitelist: true }))
  createUserDto: CreateUserDto
) {
  const user = new User(createUserDto);
  await user.save();
  return user;
}
```

The `ValidationPipe` decorator runs validation before the controller
method. NestJS enforces type narrowing before the handler runs.

Alternatively, in NestJS global setup:

```typescript
// main.ts
app.useGlobalPipes(new ValidationPipe());
```

This enforces validation on all POST/PUT requests globally.

## Async authorization race condition

### Vulnerable

```typescript
@Get('/data')
async getData(@Req() req: Request) {
  const data = await this.sensitive.fetch();
  
  const isAuthorized = await this.auth.check(req.user);
  if (!isAuthorized) {
    throw new ForbiddenException();
  }
  
  return data;
}
```

The data is fetched before authorization is checked. The data reaches
the response before the permission check completes.

### Safe

```typescript
@Get('/data')
async getData(@Req() req: Request) {
  const isAuthorized = await this.auth.check(req.user);
  if (!isAuthorized) {
    throw new ForbiddenException();
  }
  
  const data = await this.sensitive.fetch();
  return data;
}
```

Authorization check runs before data fetch. Only authorized users
receive sensitive data.

Alternatively, use a NestJS guard:

```typescript
@Get('/data')
@UseGuards(AuthzGuard)
async getData(@Req() req: Request) {
  const data = await this.sensitive.fetch();
  return data;
}
```

The guard executes before the handler, enforcing the correct order.
