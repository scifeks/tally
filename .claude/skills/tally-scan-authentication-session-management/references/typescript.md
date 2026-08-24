# TypeScript session management patterns

Vulnerable-vs-safe snippets for NestJS and typed Express session
handling that the `authentication.session_management` scanner
recognizes. Node.js shared drivers documented in
`javascript.md` apply at runtime.

## NestJS: session fixation

### Vulnerable

```typescript
@Post("login")
async login(
  @Body() dto: LoginDto,
  @Session() session: Record<string, unknown>,
): Promise<void> {
  const user = await this.authService.validate(
    dto.email,
    dto.password,
  );
  session.userId = user.id;
}
```

### Safe

```typescript
@Post("login")
async login(
  @Body() dto: LoginDto,
  @Req() req: Request,
): Promise<void> {
  const user = await this.authService.validate(
    dto.email,
    dto.password,
  );
  await new Promise<void>((resolve, reject) => {
    req.session.regenerate((err) => {
      if (err) return reject(err);
      req.session.userId = user.id;
      resolve();
    });
  });
}
```

NestJS uses `express-session` under the hood. The `@Session()`
decorator provides the session object, but regeneration requires
access to `req.session.regenerate()` via `@Req()`.

## NestJS: session configuration

### Vulnerable

```typescript
async function bootstrap() {
  const app = await NestFactory.create(AppModule);
  app.use(
    session({
      secret: process.env.SESSION_SECRET,
    }),
  );
  await app.listen(3000);
}
```

### Safe

```typescript
async function bootstrap() {
  const app = await NestFactory.create(AppModule);
  app.use(
    session({
      secret: process.env.SESSION_SECRET,
      resave: false,
      saveUninitialized: false,
      cookie: {
        secure: true,
        httpOnly: true,
        sameSite: "lax" as const,
        maxAge: 3600000,
      },
    }),
  );
  await app.listen(3000);
}
```

The `as const` assertion on `sameSite` satisfies the
`express-session` type definition, which expects a string
literal union rather than `string`.
