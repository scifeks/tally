# TypeScript authentication patterns

Vulnerable-vs-safe snippets for NestJS that the
`authentication.weak_or_missing_authn` scanner recognizes.
Express patterns from `javascript.md` apply at runtime.

## NestJS: missing guard on controller

### Vulnerable

```typescript
@Controller("users")
export class UsersController {
  @Get(":id")
  findOne(@Param("id") id: string): Promise<User> {
    return this.usersService.findOne(id);
  }
}
```

### Safe

```typescript
@Controller("users")
@UseGuards(AuthGuard("jwt"))
export class UsersController {
  @Get(":id")
  findOne(@Param("id") id: string): Promise<User> {
    return this.usersService.findOne(id);
  }
}
```

## NestJS: global guard with @Public() exemption

### Safe (global pattern)

```typescript
// app.module.ts
@Module({
  providers: [
    {
      provide: APP_GUARD,
      useClass: JwtAuthGuard,
    },
  ],
})
export class AppModule {}

// public.decorator.ts
export const IS_PUBLIC_KEY = "isPublic";
export const Public = () => SetMetadata(IS_PUBLIC_KEY, true);

// jwt-auth.guard.ts
@Injectable()
export class JwtAuthGuard extends AuthGuard("jwt") {
  canActivate(context: ExecutionContext): boolean {
    const isPublic = this.reflector.getAllAndOverride<boolean>(
      IS_PUBLIC_KEY,
      [context.getHandler(), context.getClass()],
    );
    if (isPublic) return true;
    return super.canActivate(context) as boolean;
  }
}
```

With a global guard, only routes decorated with `@Public()` are
exempt. All others require authentication by default.

## NestJS: missing guard on GraphQL resolver

### Vulnerable

```typescript
@Resolver(() => User)
export class UsersResolver {
  @Query(() => User)
  user(@Args("id") id: string): Promise<User> {
    return this.usersService.findOne(id);
  }
}
```

### Safe

```typescript
@Resolver(() => User)
@UseGuards(GqlAuthGuard)
export class UsersResolver {
  @Query(() => User)
  user(@Args("id") id: string): Promise<User> {
    return this.usersService.findOne(id);
  }
}
```

GraphQL resolvers need a dedicated `GqlAuthGuard` that extracts
the request from the GraphQL execution context rather than the
HTTP context.
