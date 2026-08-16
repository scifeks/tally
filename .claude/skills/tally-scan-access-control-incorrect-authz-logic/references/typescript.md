# TypeScript authorization logic patterns

Vulnerable-vs-safe snippets for the TypeScript frameworks and libraries
the `access_control.incorrect_authz_logic` scanner recognizes. When
multiple safe forms exist, the canonical one is shown first.

## NestJS guards and decorators

### Vulnerable

```typescript
// Overly broad @Roles decorator
@Controller('admin')
export class AdminController {
    @Post('delete-user/:id')
    @Roles(Role.User, Role.Editor, Role.Admin)
    deleteUser(@Param('id') id: number) {
        return this.userService.delete(id);
    }
}

// Guard that inverts the logic
@Injectable()
export class AdminGuard implements CanActivate {
    canActivate(context: ExecutionContext): boolean {
        const user = context.switchToHttp().getRequest().user;
        return user.role !== Role.Admin;  // Inverted!
    }
}

// Type-unsafe role comparison
if (req.user.roleId == 1) {
    performAdminAction();
}
```

### Safe

```typescript
// Only admin can access
@Controller('admin')
export class AdminController {
    @Post('delete-user/:id')
    @Roles(Role.Admin)
    deleteUser(@Param('id') id: number) {
        return this.userService.delete(id);
    }
}

// Guard that checks correctly
@Injectable()
export class AdminGuard implements CanActivate {
    canActivate(context: ExecutionContext): boolean {
        const user = context.switchToHttp().getRequest().user;
        return user.role === Role.Admin;
    }
}

// Strict equality with enum
if (req.user.roleId === Role.Admin) {
    performAdminAction();
}
```

Decorators and guards should whitelist necessary roles, not blacklist guest
roles. Always return true when access is granted.

## CASL authorization

### Vulnerable

```typescript
// Overly permissive CASL rule
export const defineAbility = (user: User) => {
    return new AbilityBuilder<Ability>(Ability as AbilityClass<Ability>)(
        ({ can }) => {
            can('read', 'Article');  // All authenticated users
            can('update', 'Article');  // Too broad
        }
    );
};

// Missing scope in rule
can('delete', 'User');  // Any user can delete any other user

// OR logic instead of AND
can('read', 'Post', { draft: true } || { published: true });
```

### Safe

```typescript
// Scoped CASL rule
export const defineAbility = (user: User) => {
    return new AbilityBuilder<Ability>(Ability as AbilityClass<Ability>)(
        ({ can }) => {
            can('read', 'Article', { published: true });
            if (user.role === Role.Editor) {
                can('update', 'Article', { author_id: user.id });
            }
            if (user.role === Role.Admin) {
                can('manage', 'Article');
            }
        }
    );
};

// Scope deletion to owner
can('delete', 'User', { id: user.id });

// AND logic with conditions
can('read', 'Post', { $and: [{ draft: true }, { author_id: user.id }] });
```

Always scope permissions to specific users, projects, or resources. A rule
without scope is too broad.

## TypeORM authorization

### Vulnerable

```typescript
// Wrong permission check
async deletePost(postId: number) {
    const post = await this.postRepository.findOne(postId);
    if (this.currentUser.hasPermission('edit')) {
        await this.postRepository.remove(post);
    }
}

// Comparison with wrong type
async updateSetting(id: number, value: any) {
    if (this.currentUser.roleId == 1) {
        return this.settingRepository.update(id, value);
    }
}

// Negated check
async accessAdmin() {
    if (this.currentUser.role !== 'guest') {
        return this.adminService.getData();
    }
}
```

### Safe

```typescript
// Check permission that matches the operation
async deletePost(postId: number) {
    const post = await this.postRepository.findOne(postId);
    if (this.currentUser.hasPermission('delete_post')) {
        await this.postRepository.remove(post);
    }
}

// Strict comparison with enum
const ROLE_ADMIN = 1;
async updateSetting(id: number, value: any) {
    if (this.currentUser.roleId === ROLE_ADMIN) {
        return this.settingRepository.update(id, value);
    }
}

// Positive assertion
async accessAdmin() {
    if (this.currentUser.role === Role.Admin) {
        return this.adminService.getData();
    }
}
```

Use permission names that describe the operation. Deleting requires
'delete_post', not 'edit'. Use strict equality and role enums.

## Passport.js with custom authorization

### Vulnerable

```typescript
// Overly broad role list
app.get('/delete-resource/:id', (req, res) => {
    if (req.user && 
        ['admin', 'moderator', 'editor', 'user'].includes(
            req.user.role
        )) {
        deleteResource(req.params.id);
    }
});

// OR instead of AND
if (user.hasPermission('create') || user.hasPermission('read')) {
    performSensitiveAction();
}

// Missing null check before role access
const role = req.user.role;
if (role === 'admin') {
    adminAction();
}
```

### Safe

```typescript
// Only necessary roles
const ALLOWED_DELETE_ROLES = ['admin', 'moderator'];
app.get('/delete-resource/:id', (req, res) => {
    if (req.user && 
        ALLOWED_DELETE_ROLES.includes(req.user.role)) {
        deleteResource(req.params.id);
    }
});

// AND when both conditions must hold
if (user.hasPermission('create') && user.hasPermission('review')) {
    performSensitiveAction();
}

// Null-safe and type-safe
const role = req.user?.role;
if (role === Role.Admin) {
    adminAction();
}
```

Define allowed roles as constants and use AND logic when multiple
conditions must hold. Always null-check before accessing user properties.
