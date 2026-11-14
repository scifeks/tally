# TypeScript IDOR/BOLA patterns

Vulnerable-vs-safe snippets for the TypeScript frameworks and ORMs the
`access_control.idor_bola` scanner recognizes. When multiple safe forms
exist, the canonical one is shown first.

## Prisma

### Vulnerable

```typescript
export async function getUser(userId: string) {
    const user = await prisma.user.findUnique({
        where: { id: userId }
    });
    return user;
}
```

```typescript
@Post('/update-post/:postId')
async updatePost(@Param('postId') postId: string, @Body() body: any) {
    const post = await prisma.post.findUnique({
        where: { id: postId }
    });
    post.title = body.title;
    await prisma.post.update({
        where: { id: postId },
        data: { title: body.title }
    });
    return post;
}
```

### Safe

```typescript
export async function getUser(userId: string, currentUserId: string) {
    const user = await prisma.user.findFirst({
        where: {
            id: userId,
            id: currentUserId
        }
    });
    if (!user) throw new Error('Not found');
    return user;
}
```

```typescript
@Post('/update-post/:postId')
async updatePost(
    @Param('postId') postId: string,
    @Body() body: any,
    @Request() req: any
) {
    const post = await prisma.post.findFirst({
        where: {
            id: postId,
            author_id: req.user.id
        }
    });
    if (!post) throw new HttpException('Not found', 404);
    await prisma.post.update({
        where: { id: postId },
        data: { title: body.title }
    });
    return post;
}
```

The safe patterns use `findFirst` with an ownership filter or raise an
exception if the resource is not found.

## TypeORM

### Vulnerable

```typescript
async getRepository(id: string) {
    return this.repositoryRepository.findOneBy({ id });
}
```

```typescript
@Get('/:docId')
async getDocument(@Param('docId') docId: string) {
    const doc = await this.documentRepository.findOneBy({ id: docId });
    return doc;
}
```

### Safe

```typescript
async getRepository(id: string, userId: string) {
    return this.repositoryRepository.findOneBy({
        id,
        owner_id: userId
    });
}
```

```typescript
@Get('/:docId')
async getDocument(
    @Param('docId') docId: string,
    @Request() req: any
) {
    const doc = await this.documentRepository.findOneBy({
        id: docId,
        owner_id: req.user.id
    });
    if (!doc) throw new HttpException('Not found', 404);
    return doc;
}
```

The safe pattern adds an ownership filter to the query.

## NestJS with Guards

### Vulnerable

```typescript
@Controller('items')
export class ItemController {
    @Get(':id')
    async getItem(@Param('id') id: string) {
        return this.itemService.findOne(id);
    }
}
```

### Safe

```typescript
@Controller('items')
export class ItemController {
    @Get(':id')
    @UseGuards(AuthGuard('jwt'))
    async getItem(
        @Param('id') id: string,
        @Request() req: any
    ) {
        const item = await this.itemService.findOne(id);
        if (!item || item.owner_id !== req.user.id) {
            throw new ForbiddenException('Access denied');
        }
        return item;
    }
}
```

The safe pattern uses an `@UseGuards` decorator to ensure authentication,
then verifies ownership in the handler.

## NestJS with Interceptor

### Vulnerable

```typescript
@Controller('orders')
export class OrderController {
    @Get(':id')
    async getOrder(@Param('id') id: string) {
        return this.orderService.findOne(id);
    }
}
```

### Safe

```typescript
@Injectable()
export class OwnershipInterceptor implements NestInterceptor {
    constructor(private orderService: OrderService) {}

    async intercept(
        context: ExecutionContext,
        next: CallHandler
    ): Promise<Observable<any>> {
        const req = context.switchToHttp().getRequest();
        const orderId = req.params.id;
        const order = await this.orderService.findOne(orderId);

        if (!order || order.user_id !== req.user.id) {
            throw new ForbiddenException('Access denied');
        }
        return next.handle();
    }
}

@Controller('orders')
@UseInterceptors(OwnershipInterceptor)
export class OrderController {
    @Get(':id')
    async getOrder(@Param('id') id: string) {
        return this.orderService.findOne(id);
    }
}
```

The safe pattern uses an interceptor to verify ownership before the
handler runs.

## Express with TypeScript

### Vulnerable

```typescript
app.get('/api/post/:postId', async (req: Request, res: Response) => {
    const post = await Post.findById(req.params.postId);
    res.json(post);
});
```

### Safe

```typescript
app.get('/api/post/:postId', async (req: Request, res: Response) => {
    const post = await Post.findOne({
        _id: req.params.postId,
        author_id: (req as any).user.id
    });
    if (!post) return res.status(404).json({error: 'Not found'});
    res.json(post);
});
```

The safe pattern adds an ownership filter.

## Sequelize (TypeScript)

### Vulnerable

```typescript
async getPost(postId: string) {
    return await Post.findByPk(postId);
}
```

### Safe

```typescript
async getPost(postId: string, userId: string) {
    return await Post.findOne({
        where: {
            id: postId,
            user_id: userId
        }
    });
}
```

The safe pattern filters by both the resource ID and the user ID.

## Multi-tenant with NestJS

### Vulnerable

```typescript
@Get(':tenantId')
async getTenant(@Param('tenantId') tenantId: string) {
    return this.tenantService.findOne(tenantId);
}
```

### Safe

```typescript
@Get(':tenantId')
@UseGuards(AuthGuard('jwt'))
async getTenant(
    @Param('tenantId') tenantId: string,
    @Request() req: any
) {
    const tenant = await this.tenantService.findOne(tenantId);
    if (!tenant || !tenant.members.includes(req.user.id)) {
        throw new ForbiddenException('Access denied');
    }
    return tenant;
}
```

The safe pattern verifies the authenticated user is a member of the
tenant.
