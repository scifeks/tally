# JavaScript missing function-level authorization patterns

Vulnerable-vs-safe snippets for the JavaScript frameworks the
`access_control.missing_function_authz` scanner recognizes. When
multiple safe forms exist, the canonical one is shown first.

## Express.js

### Vulnerable

```javascript
const express = require('express');
const app = express();

// POST endpoint with no auth middleware
app.post('/users', (req, res) => {
    // Any user can create users
    const user = User.create({ email: req.body.email });
    res.json({ id: user.id });
});

// PUT endpoint without auth check
app.put('/users/:id', (req, res) => {
    // State-changing without authorization
    const user = User.findById(req.params.id);
    user.is_admin = req.body.is_admin;
    user.save();
    res.json({ status: 'ok' });
});

// Router group without auth middleware
const adminRouter = express.Router();
adminRouter.post('/delete-user', (req, res) => {
    // Unprotected admin action
    User.findByIdAndDelete(req.body.user_id);
    res.json({ status: 'ok' });
});
app.use('/admin', adminRouter);
```

### Safe

```javascript
const express = require('express');
const app = express();

// Auth middleware
const authMiddleware = (req, res, next) => {
    const token = req.headers.authorization?.split(' ')[1];
    try {
        const user = verifyToken(token);
        req.user = user;
        next();
    } catch (err) {
        res.status(403).json({ error: 'Unauthorized' });
    }
};

// POST endpoint with auth middleware in chain
app.post('/users', authMiddleware, (req, res) => {
    const user = User.create({ email: req.body.email });
    res.json({ id: user.id });
});

// PUT endpoint with auth middleware
app.put('/users/:id', authMiddleware, (req, res) => {
    const user = User.findById(req.params.id);
    user.is_admin = req.body.is_admin;
    user.save();
    res.json({ status: 'ok' });
});

// Router group with auth middleware
const adminRouter = express.Router();
adminRouter.post('/delete-user', authMiddleware, (req, res) => {
    if (req.user.role !== 'admin') {
        return res.status(403).json({ error: 'Forbidden' });
    }
    User.findByIdAndDelete(req.body.user_id);
    res.json({ status: 'ok' });
});
app.use('/admin', adminRouter);
```

Alternatively, protect the entire router:

```javascript
const adminRouter = express.Router();

// All routes on adminRouter require auth
adminRouter.use(authMiddleware);
adminRouter.use((req, res, next) => {
    if (req.user.role !== 'admin') {
        return res.status(403).json({ error: 'Forbidden' });
    }
    next();
});

adminRouter.post('/delete-user', (req, res) => {
    User.findByIdAndDelete(req.body.user_id);
    res.json({ status: 'ok' });
});

app.use('/admin', adminRouter);
```

## Koa

### Vulnerable

```javascript
const Koa = require('koa');
const app = new Koa();

// POST endpoint with no auth middleware
app.use(async (ctx) => {
    if (ctx.path === '/users' && ctx.method === 'POST') {
        // Any user can create users
        const user = await User.create({ email: ctx.request.body.email });
        ctx.body = { id: user.id };
    }
});

// PUT endpoint without auth check
app.use(async (ctx) => {
    if (ctx.path.startsWith('/users/') && ctx.method === 'PUT') {
        // State-changing without authorization
        const user = await User.findById(ctx.params.id);
        user.is_admin = ctx.request.body.is_admin;
        await user.save();
        ctx.body = { status: 'ok' };
    }
});
```

### Safe

```javascript
const Koa = require('koa');
const Router = require('koa-router');

const app = new Koa();
const router = new Router();

// Auth middleware
const authMiddleware = async (ctx, next) => {
    const token = ctx.headers.authorization?.split(' ')[1];
    try {
        ctx.user = verifyToken(token);
        await next();
    } catch (err) {
        ctx.status = 403;
        ctx.body = { error: 'Unauthorized' };
    }
};

// POST endpoint with auth middleware in chain
router.post(
    '/users',
    authMiddleware,
    async (ctx) => {
        const user = await User.create({
            email: ctx.request.body.email,
        });
        ctx.body = { id: user.id };
    }
);

// PUT endpoint with auth middleware
router.put(
    '/users/:id',
    authMiddleware,
    async (ctx) => {
        const user = await User.findById(ctx.params.id);
        user.is_admin = ctx.request.body.is_admin;
        await user.save();
        ctx.body = { status: 'ok' };
    }
);

// Admin routes with auth and role check
const adminRouter = new Router({ prefix: '/admin' });
adminRouter.use(authMiddleware);
adminRouter.use(async (ctx, next) => {
    if (ctx.user.role !== 'admin') {
        ctx.status = 403;
        ctx.body = { error: 'Forbidden' };
        return;
    }
    await next();
});

adminRouter.post('/delete-user', async (ctx) => {
    await User.findByIdAndDelete(ctx.request.body.user_id);
    ctx.body = { status: 'ok' };
});

app.use(router.routes());
app.use(adminRouter.routes());
```

## Passport.js with Express

### Vulnerable

```javascript
const express = require('express');
const app = express();

// POST endpoint without Passport auth
app.post('/users', (req, res) => {
    // Any user can create users
    const user = User.create({ email: req.body.email });
    res.json({ id: user.id });
});

// Router without Passport guards
const adminRouter = express.Router();
adminRouter.post('/grant-admin', (req, res) => {
    // No auth check; anyone can grant admin role
    const user = User.findById(req.body.user_id);
    user.role = 'admin';
    user.save();
    res.json({ status: 'ok' });
});
app.use('/admin', adminRouter);
```

### Safe

```javascript
const express = require('express');
const passport = require('passport');
const LocalStrategy = require('passport-local').Strategy;

const app = express();

// Configure Passport strategy
passport.use(new LocalStrategy({
    usernameField: 'email',
    passwordField: 'password',
}, async (email, password, done) => {
    try {
        const user = await User.findOne({ email });
        if (!user || !user.validPassword(password)) {
            return done(null, false, { message: 'Invalid' });
        }
        return done(null, user);
    } catch (err) {
        return done(err);
    }
}));

passport.serializeUser((user, done) => {
    done(null, user.id);
});

passport.deserializeUser(async (id, done) => {
    try {
        const user = await User.findById(id);
        done(null, user);
    } catch (err) {
        done(err);
    }
});

// POST endpoint with Passport auth
app.post(
    '/users',
    passport.authenticate('local'),
    (req, res) => {
        const user = User.create({ email: req.body.email });
        res.json({ id: user.id });
    }
);

// Router with Passport guards
const adminRouter = express.Router();
adminRouter.use((req, res, next) => {
    if (!req.isAuthenticated() || req.user.role !== 'admin') {
        return res.status(403).json({ error: 'Forbidden' });
    }
    next();
});

adminRouter.post('/grant-admin', (req, res) => {
    const user = User.findById(req.body.user_id);
    user.role = 'admin';
    user.save();
    res.json({ status: 'ok' });
});

app.use('/admin', adminRouter);
```
