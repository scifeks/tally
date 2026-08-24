# JavaScript insufficient logging patterns

Vulnerable-vs-safe snippets for Node.js auth middleware (Express, Koa,
Fastify) and admin operations lacking audit trails.

## Express auth middleware without logging

### Vulnerable

```javascript
const authMiddleware = (req, res, next) => {
    const token = req.headers.authorization?.split(' ')[1];
    if (!token) {
        return res.status(401).send({ error: 'Missing token' });
    }
    try {
        const payload = jwt.verify(token, SECRET);
        req.user = payload;
        next();
    } catch (err) {
        return res.status(401).send({ error: 'Invalid token' });
    }
};

app.use(authMiddleware);
```

### Safe

```javascript
const logger = require('winston').createLogger({...});

const authMiddleware = (req, res, next) => {
    const token = req.headers.authorization?.split(' ')[1];
    if (!token) {
        logger.warn('API access without token', {
            path: req.path,
            ip: req.ip,
        });
        return res.status(401).send({ error: 'Missing token' });
    }
    try {
        const payload = jwt.verify(token, SECRET);
        req.user = payload;
        logger.info('User authenticated', {
            user_id: payload.user_id,
            path: req.path,
            ip: req.ip,
        });
        next();
    } catch (err) {
        logger.warn('Invalid token provided', {
            path: req.path,
            ip: req.ip,
        });
        return res.status(401).send({ error: 'Invalid token' });
    }
};

app.use(authMiddleware);
```

Log both successful auth and all failures with timestamp, user ID, and
client IP.

## Promise-based auth with unhandled rejection

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
```

### Safe

```javascript
const logger = require('pino')();

const authMiddleware = (req, res, next) => {
    const token = req.headers.authorization?.split(' ')[1];
    if (!token) {
        logger.warn({ path: req.path, ip: req.ip }, 'Missing token');
        return res.status(401).send({ error: 'Missing token' });
    }
    jwt.verify(token, SECRET)
        .then(payload => {
            req.user = payload;
            logger.info(
                { user_id: payload.user_id, path: req.path },
                'Auth success'
            );
            next();
        })
        .catch(err => {
            logger.warn(
                { path: req.path, ip: req.ip, error: err.message },
                'Token verification failed'
            );
            res.status(401).send({ error: 'Invalid token' });
        });
};

app.use(authMiddleware);
```

Always attach a `.catch()` handler and log the error before responding.

## Permission check without logging

### Vulnerable

```javascript
const requireAdmin = (req, res, next) => {
    if (!req.user?.isAdmin) {
        return res.status(403).send({ error: 'Not admin' });
    }
    next();
};

app.delete('/admin/users/:id', requireAdmin, (req, res) => {
    User.findByIdAndDelete(req.params.id);
    res.send({ status: 'deleted' });
});
```

### Safe

```javascript
const logger = require('winston').createLogger({...});

const requireAdmin = (req, res, next) => {
    if (!req.user?.isAdmin) {
        logger.warn('Non-admin access to admin endpoint', {
            user_id: req.user?.id,
            path: req.path,
            ip: req.ip,
        });
        return res.status(403).send({ error: 'Not admin' });
    }
    logger.info('Admin access granted', {
        user_id: req.user.id,
        path: req.path,
    });
    next();
};

app.delete('/admin/users/:id', requireAdmin, (req, res) => {
    const deletedId = req.params.id;
    logger.info('User deleted by admin', {
        admin_id: req.user.id,
        deleted_user_id: deletedId,
        ip: req.ip,
    });
    User.findByIdAndDelete(deletedId);
    res.send({ status: 'deleted' });
});
```

Log both permission denials and approvals for admin endpoints.

## Login endpoint without logging

### Vulnerable

```javascript
app.post('/login', async (req, res) => {
    const { email, password } = req.body;
    const user = await User.findOne({ email });
    if (!user || !(await user.checkPassword(password))) {
        return res.status(401).send({ error: 'Invalid credentials' });
    }
    req.session.userId = user.id;
    res.send({ status: 'logged in' });
});
```

### Safe

```javascript
const logger = require('pino')();

app.post('/login', async (req, res) => {
    const { email, password } = req.body;
    const user = await User.findOne({ email });
    if (!user || !(await user.checkPassword(password))) {
        logger.warn(
            { email, ip: req.ip },
            'Login failed'
        );
        return res.status(401).send({ error: 'Invalid credentials' });
    }
    logger.info(
        { user_id: user.id, email, ip: req.ip },
        'User login successful'
    );
    req.session.userId = user.id;
    res.send({ status: 'logged in' });
});
```

Log both successful and failed login attempts with user identity,
timestamp, and client IP.

## Rate limit silently failing open

### Vulnerable

```javascript
const checkRateLimit = async (req, res, next) => {
    try {
        const key = `rate_limit:${req.user.id}`;
        const count = await redis.incr(key);
        if (count > 100) {
            return res.status(429).send({ error: 'Too many requests' });
        }
        next();
    } catch (err) {
        // Redis failure silently ignored; request proceeds
        next();
    }
};

app.use(checkRateLimit);
```

### Safe

```javascript
const logger = require('winston').createLogger({...});

const checkRateLimit = async (req, res, next) => {
    try {
        const key = `rate_limit:${req.user.id}`;
        const count = await redis.incr(key);
        if (count > 100) {
            logger.warn('Rate limit exceeded', {
                user_id: req.user.id,
                count,
                ip: req.ip,
            });
            return res.status(429).send({ error: 'Too many requests' });
        }
        next();
    } catch (err) {
        logger.error('Rate limiter backend failure', {
            error: err.message,
            user_id: req.user.id,
        });
        res.status(503).send({ error: 'Service unavailable' });
    }
};

app.use(checkRateLimit);
```

Log both rate limit violations and backend failures. Return 503 when the
rate limiter is unavailable, not 200.

## Admin API endpoint without logging

### Vulnerable

```javascript
app.post('/admin/api/users', async (req, res) => {
    const user = await User.create(req.body);
    res.json({ id: user.id });
});

app.delete('/admin/api/users/:id', async (req, res) => {
    await User.findByIdAndDelete(req.params.id);
    res.json({ status: 'deleted' });
});
```

### Safe

```javascript
const logger = require('pino')();

app.post('/admin/api/users', async (req, res) => {
    const admin = req.user;
    const user = await User.create(req.body);
    logger.info(
        {
            admin_id: admin.id,
            created_user_id: user.id,
            email: user.email,
            ip: req.ip,
        },
        'User created via API'
    );
    res.json({ id: user.id });
});

app.delete('/admin/api/users/:id', async (req, res) => {
    const admin = req.user;
    const deletedId = req.params.id;
    logger.info(
        {
            admin_id: admin.id,
            deleted_user_id: deletedId,
            ip: req.ip,
        },
        'User deleted via API'
    );
    await User.findByIdAndDelete(deletedId);
    res.json({ status: 'deleted' });
});
```

Log all admin state-changing operations with the acting admin's ID,
timestamp, and action details.

## Koa middleware silently catching auth

### Vulnerable

```javascript
const authMiddleware = async (ctx, next) => {
    const token = ctx.headers.authorization?.split(' ')[1];
    try {
        const payload = jwt.verify(token, SECRET);
        ctx.state.user = payload;
    } catch (err) {
        // Exception swallowed; middleware continues
    }
    await next();
};

app.use(authMiddleware);
```

### Safe

```javascript
const logger = require('winston').createLogger({...});

const authMiddleware = async (ctx, next) => {
    const token = ctx.headers.authorization?.split(' ')[1];
    try {
        if (!token) {
            logger.warn('Missing token', { path: ctx.path, ip: ctx.ip });
            ctx.status = 401;
            ctx.body = { error: 'Missing token' };
            return;
        }
        const payload = jwt.verify(token, SECRET);
        ctx.state.user = payload;
        logger.info('User authenticated', {
            user_id: payload.user_id,
            path: ctx.path,
        });
    } catch (err) {
        logger.warn('Token verification failed', {
            path: ctx.path,
            ip: ctx.ip,
            error: err.message,
        });
        ctx.status = 401;
        ctx.body = { error: 'Invalid token' };
        return;
    }
    await next();
};

app.use(authMiddleware);
```

Log auth failures before responding. Set status and body, then return
early.
