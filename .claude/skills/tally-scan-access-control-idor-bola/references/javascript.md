# JavaScript IDOR/BOLA patterns

Vulnerable-vs-safe snippets for the JavaScript (Node.js) frameworks and
ORMs the `access_control.idor_bola` scanner recognizes. When multiple safe
forms exist, the canonical one is shown first.

## Mongoose (MongoDB)

### Vulnerable

```javascript
app.get('/api/user/:userId', (req, res) => {
    User.findById(req.params.userId, (err, user) => {
        res.json(user);
    });
});
```

```javascript
app.post('/api/orders/:orderId', async (req, res) => {
    const order = await Order.findById(req.params.orderId);
    order.status = 'shipped';
    await order.save();
    res.json(order);
});
```

### Safe

```javascript
app.get('/api/user/:userId', (req, res) => {
    User.findOne({
        _id: req.params.userId,
        _id: req.user._id
    }, (err, user) => {
        if (!user) return res.status(404).json({error: 'Not found'});
        res.json(user);
    });
});
```

```javascript
app.post('/api/orders/:orderId', async (req, res) => {
    const order = await Order.findOne({
        _id: req.params.orderId,
        user_id: req.user._id
    });
    if (!order) return res.status(404).json({error: 'Not found'});
    order.status = 'shipped';
    await order.save();
    res.json(order);
});
```

The safe patterns use `findOne` with multiple conditions, including the
ownership filter, or raise a 404 if the resource is not found.

## Sequelize (SQL)

### Vulnerable

```javascript
app.get('/api/posts/:postId', async (req, res) => {
    const post = await Post.findOne({
        where: { id: req.params.postId }
    });
    res.json(post);
});
```

### Safe

```javascript
app.get('/api/posts/:postId', async (req, res) => {
    const post = await Post.findOne({
        where: {
            id: req.params.postId,
            user_id: req.user.id
        }
    });
    if (!post) return res.status(404).json({error: 'Not found'});
    res.json(post);
});
```

The safe pattern adds a user ownership filter to the WHERE clause.

## Knex Query Builder

### Vulnerable

```javascript
app.get('/api/documents/:docId', async (req, res) => {
    const doc = await knex('documents')
        .where({id: req.params.docId})
        .first();
    res.json(doc);
});
```

### Safe

```javascript
app.get('/api/documents/:docId', async (req, res) => {
    const doc = await knex('documents')
        .where({id: req.params.docId})
        .where({owner_id: req.user.id})
        .first();
    if (!doc) return res.status(404).json({error: 'Not found'});
    res.json(doc);
});
```

The safe pattern adds an ownership WHERE clause.

## Raw SQL with Express

### Vulnerable

```javascript
app.get('/api/profile/:userId', (req, res) => {
    const query = `SELECT * FROM users WHERE id = ${req.params.userId}`;
    db.query(query, (err, result) => {
        res.json(result[0]);
    });
});
```

### Safe

```javascript
app.get('/api/profile/:userId', (req, res) => {
    const userId = parseInt(req.params.userId);
    const currentUserId = req.user.id;
    if (userId !== currentUserId && !req.user.isAdmin) {
        return res.status(403).json({error: 'Forbidden'});
    }
    const query = 'SELECT * FROM users WHERE id = ?';
    db.query(query, [userId], (err, result) => {
        res.json(result[0]);
    });
});
```

The safe pattern checks ownership before querying and uses parameterized
queries.

## Express with Middleware

### Vulnerable

```javascript
app.get('/api/settings/:userId', (req, res) => {
    Settings.findOne({ user_id: req.params.userId }, (err, settings) => {
        res.json(settings);
    });
});
```

### Safe

```javascript
const checkOwnership = (req, res, next) => {
    if (parseInt(req.params.userId) !== req.user.id && !req.user.isAdmin) {
        return res.status(403).json({error: 'Forbidden'});
    }
    next();
};

app.get('/api/settings/:userId', checkOwnership, (req, res) => {
    Settings.findOne({ user_id: req.params.userId }, (err, settings) => {
        res.json(settings);
    });
});
```

The safe pattern uses middleware to check ownership before the handler
runs.

## TypeORM (when used in JavaScript/Node)

### Vulnerable

```javascript
app.get('/api/items/:itemId', async (req, res) => {
    const item = await itemRepository.findOne({id: req.params.itemId});
    res.json(item);
});
```

### Safe

```javascript
app.get('/api/items/:itemId', async (req, res) => {
    const item = await itemRepository.findOne({
        where: {
            id: req.params.itemId,
            owner_id: req.user.id
        }
    });
    if (!item) return res.status(404).json({error: 'Not found'});
    res.json(item);
});
```

The safe pattern adds an ownership filter to the WHERE clause.

## Multi-tenant filtering

For applications with multiple tenants, filter by both the resource ID and
the tenant:

### Vulnerable

```javascript
app.get('/api/workspace/:workspaceId', async (req, res) => {
    const workspace = await Workspace.findById(req.params.workspaceId);
    res.json(workspace);
});
```

### Safe

```javascript
app.get('/api/workspace/:workspaceId', async (req, res) => {
    const workspace = await Workspace.findOne({
        _id: req.params.workspaceId,
        members: req.user._id
    });
    if (!workspace) return res.status(404).json({error: 'Not found'});
    res.json(workspace);
});
```

The safe pattern verifies the authenticated user is a member of the
workspace.
