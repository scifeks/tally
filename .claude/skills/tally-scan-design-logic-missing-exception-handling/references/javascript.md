# JavaScript missing exception handling patterns

Vulnerable-vs-safe snippets for Node.js auth middleware (Express,
Koa, Fastify) and async/await patterns.

## Express middleware with next() in catch

### Vulnerable

```javascript
const authMiddleware = (req, res, next) => {
    try {
        const token = req.headers.authorization?.split(' ')[1];
        const payload = jwt.verify(token, SECRET);
        req.user = payload;
    } catch (err) {
        next();  // next() without error; request proceeds
    }
};

app.use(authMiddleware);
app.get('/admin', (req, res) => {
    if (!req.user?.isAdmin) {
        return res.status(403).send('Not admin');
    }
    res.send('Admin panel');
});
```

### Safe

```javascript
const authMiddleware = (req, res, next) => {
    try {
        const token = req.headers.authorization?.split(' ')[1];
        if (!token) {
            return res.status(401).send('Missing token');
        }
        const payload = jwt.verify(token, SECRET);
        req.user = payload;
        next();
    } catch (err) {
        return res.status(401).send('Invalid token');
    }
};

app.use(authMiddleware);
app.get('/admin', (req, res) => {
    if (!req.user?.isAdmin) {
        return res.status(403).send('Not admin');
    }
    res.send('Admin panel');
});
```

In the catch block, return an error response with `next(err)` or
`res.status(401)`. Never call `next()` without arguments after an auth
failure.

## Promise-based auth without catch handler

### Vulnerable

```javascript
const authMiddleware = (req, res, next) => {
    const token = req.headers.authorization?.split(' ')[1];
    jwt.verify(token, SECRET)
        .then(payload => {
            req.user = payload;
            next();
        });
        // No .catch() handler; unhandled rejection
};

app.use(authMiddleware);
app.get('/admin', (req, res) => {
    res.send(`Welcome ${req.user.name}`);  // req.user undefined if verify fails
});
```

### Safe

```javascript
const authMiddleware = (req, res, next) => {
    const token = req.headers.authorization?.split(' ')[1];
    if (!token) {
        return res.status(401).send('Missing token');
    }
    jwt.verify(token, SECRET)
        .then(payload => {
            req.user = payload;
            next();
        })
        .catch(err => {
            res.status(401).send('Invalid token');
        });
};

app.use(authMiddleware);
app.get('/admin', (req, res) => {
    res.send(`Welcome ${req.user.name}`);
});
```

Always attach a `.catch()` handler to promise-based auth checks. Return
an error response in the catch block.

## Async middleware with silent exception

### Vulnerable

```javascript
const authMiddleware = async (req, res, next) => {
    try {
        const token = req.headers.authorization?.split(' ')[1];
        const payload = await jwt.verify(token, SECRET);
        req.user = payload;
    } catch (err) {
        // Exception caught; no error passed to next
        next();
    }
};

app.use(authMiddleware);
```

### Safe

```javascript
const authMiddleware = async (req, res, next) => {
    try {
        const token = req.headers.authorization?.split(' ')[1];
        if (!token) {
            return res.status(401).send('Missing token');
        }
        const payload = await jwt.verify(token, SECRET);
        req.user = payload;
        next();
    } catch (err) {
        res.status(401).send('Invalid token');
    }
};

app.use(authMiddleware);
```

In catch blocks, return a 401 response or call `next(err)`. Do not call
`next()` without arguments.

## Koa middleware with fail-open

### Vulnerable

```javascript
const authMiddleware = async (ctx, next) => {
    try {
        const token = ctx.headers.authorization?.split(' ')[1];
        const payload = jwt.verify(token, SECRET);
        ctx.state.user = payload;
    } catch (err) {
        // Exception swallowed; middleware continues
    }
    await next();
};

app.use(authMiddleware);
app.get('/admin', (ctx) => {
    if (!ctx.state.user?.isAdmin) {
        ctx.status = 403;
        ctx.body = { error: 'Not admin' };
        return;
    }
    ctx.body = { data: 'Admin panel' };
});
```

### Safe

```javascript
const authMiddleware = async (ctx, next) => {
    try {
        const token = ctx.headers.authorization?.split(' ')[1];
        if (!token) {
            ctx.status = 401;
            ctx.body = { error: 'Missing token' };
            return;
        }
        const payload = jwt.verify(token, SECRET);
        ctx.state.user = payload;
    } catch (err) {
        ctx.status = 401;
        ctx.body = { error: 'Invalid token' };
        return;
    }
    await next();
};

app.use(authMiddleware);
app.get('/admin', (ctx) => {
    if (!ctx.state.user?.isAdmin) {
        ctx.status = 403;
        ctx.body = { error: 'Not admin' };
        return;
    }
    ctx.body = { data: 'Admin panel' };
});
```

Set the appropriate status and body on the context. Return early to
prevent `await next()` from executing.

## Fastify hook with done() in catch

### Vulnerable

```javascript
fastify.addHook('onRequest', async (request, reply) => {
    try {
        const token = request.headers.authorization?.split(' ')[1];
        const payload = await jwt.verify(token, SECRET);
        request.user = payload;
    } catch (err) {
        reply.code(200);  // Returns 200 on auth failure
    }
});

fastify.get('/admin', (request, reply) => {
    if (!request.user?.isAdmin) {
        return reply.code(403).send({ error: 'Not admin' });
    }
    reply.send({ data: 'Admin panel' });
});
```

### Safe

```javascript
fastify.addHook('onRequest', async (request, reply) => {
    try {
        const token = request.headers.authorization?.split(' ')[1];
        if (!token) {
            return reply.code(401).send({ error: 'Missing token' });
        }
        const payload = await jwt.verify(token, SECRET);
        request.user = payload;
    } catch (err) {
        return reply.code(401).send({ error: 'Invalid token' });
    }
});

fastify.get('/admin', (request, reply) => {
    if (!request.user?.isAdmin) {
        return reply.code(403).send({ error: 'Not admin' });
    }
    reply.send({ data: 'Admin panel' });
});
```

Return early with the error response. Do not fall through to the next
handler.

## Generic async check with unhandled rejection

### Vulnerable

```javascript
const checkPermission = async (req, res, next) => {
    const permission = await db.getPermission(req.user.id);
    if (permission.level < 5) {
        throw new Error('Insufficient permissions');
    }
    next();
};

app.get('/protected', checkPermission, (req, res) => {
    res.send('Protected data');
});
// If db.getPermission rejects, the error is not caught in the route
```

### Safe

```javascript
const checkPermission = async (req, res, next) => {
    try {
        const permission = await db.getPermission(req.user.id);
        if (permission.level < 5) {
            return res.status(403).send('Insufficient permissions');
        }
        next();
    } catch (err) {
        res.status(500).send('Service error');
    }
};

app.get(
    '/protected',
    checkPermission,
    (req, res) => {
        res.send('Protected data');
    }
);
```

Wrap async operations in try/catch. Return error responses in catch
blocks.
