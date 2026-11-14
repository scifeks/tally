# JavaScript CSRF patterns

Vulnerable-vs-safe snippets for the JavaScript (Node.js) frameworks the
`access_control.csrf` scanner recognizes. When multiple safe forms exist,
the canonical one is shown first.

## Express

### Vulnerable

```javascript
const express = require('express');
const app = express();

app.post('/user/update', (req, res) => {
    const name = req.body.name;
    user.name = name;
    user.save();
    res.json({ status: 'ok' });
});
```

### Safe

```javascript
const express = require('express');
const cookieParser = require('cookie-parser');
const csurf = require('csurf');
const app = express();

app.use(express.urlencoded({ extended: false }));
app.use(cookieParser());
app.use(csurf({ cookie: true }));

app.get('/user', (req, res) => {
    res.send(`
        <form action="/user/update" method="POST">
            <input type="hidden" name="_csrf" value="${req.csrfToken()}">
            <input type="text" name="name">
            <input type="submit">
        </form>
    `);
});

app.post('/user/update', (req, res) => {
    const name = req.body.name;
    user.name = name;
    user.save();
    res.json({ status: 'ok' });
});
```

Install `csurf` and `cookie-parser`, then register the middleware:
`app.use(csurf({ cookie: true }))`. On GET, call `req.csrfToken()` and
pass it to the template. The middleware validates the token on POST
automatically.

For AJAX requests, include the token in a header:

```javascript
// Client-side
const token = document.querySelector('meta[name="csrf-token"]').content;
fetch('/user/update', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': token,
    },
    body: JSON.stringify({ name: 'new name' }),
});
```

## Koa

### Vulnerable

```javascript
const Koa = require('koa');
const app = new Koa();

app.use(async (ctx) => {
    if (ctx.method === 'POST' && ctx.path === '/user/update') {
        const name = ctx.request.body.name;
        user.name = name;
        user.save();
        ctx.body = { status: 'ok' };
    }
});
```

### Safe

```javascript
const Koa = require('koa');
const csrf = require('koa-csrf');
const app = new Koa();

app.use(csrf());

app.use(async (ctx) => {
    if (ctx.method === 'GET' && ctx.path === '/user') {
        ctx.body = `
            <form action="/user/update" method="POST">
                <input type="hidden" name="_csrf" value="${ctx.csrf}">
                <input type="text" name="name">
                <input type="submit">
            </form>
        `;
    }
    if (ctx.method === 'POST' && ctx.path === '/user/update') {
        const name = ctx.request.body.name;
        user.name = name;
        user.save();
        ctx.body = { status: 'ok' };
    }
});
```

Install `koa-csrf` and register it as middleware:
`app.use(csrf())`. The middleware validates the token on POST and
provides `ctx.csrf` for templates.

## Hapi

### Vulnerable

```javascript
const Hapi = require('@hapi/hapi');

const init = async () => {
    const server = Hapi.server({ port: 3000 });

    server.route({
        method: 'POST',
        path: '/user/update',
        handler: (request, h) => {
            const name = request.payload.name;
            user.name = name;
            user.save();
            return { status: 'ok' };
        },
    });
};
```

### Safe

```javascript
const Hapi = require('@hapi/hapi');

const init = async () => {
    const server = Hapi.server({ port: 3000 });

    await server.register(require('@hapi/crumb'));

    server.route({
        method: 'GET',
        path: '/user',
        handler: (request, h) => {
            return `
                <form action="/user/update" method="POST">
                    <input type="hidden" name="crumb"
                        value="${request.server.plugins.crumb}">
                    <input type="text" name="name">
                    <input type="submit">
                </form>
            `;
        },
    });

    server.route({
        method: 'POST',
        path: '/user/update',
        handler: (request, h) => {
            const name = request.payload.name;
            user.name = name;
            user.save();
            return { status: 'ok' };
        },
    });

    await server.start();
};
```

Install and register the `@hapi/crumb` plugin:
`await server.register(require('@hapi/crumb'))`. The plugin validates
tokens on POST automatically and provides the token via
`request.server.plugins.crumb`.

## Cookie-based sessions (generic Node.js)

### Vulnerable

```javascript
const express = require('express');
const session = require('express-session');
const app = express();

app.use(session({ secret: 'secret', resave: false }));

app.post('/user/update', (req, res) => {
    if (!req.session.user) {
        return res.status(401).json({ error: 'Not authenticated' });
    }
    const name = req.body.name;
    user.name = name;
    user.save();
    res.json({ status: 'ok' });
});
```

### Safe

```javascript
const express = require('express');
const session = require('express-session');
const crypto = require('crypto');
const app = express();

app.use(session({ secret: 'secret', resave: false }));

app.get('/user', (req, res) => {
    if (!req.session.csrfToken) {
        req.session.csrfToken = crypto.randomBytes(32).toString('hex');
    }
    res.send(`
        <form action="/user/update" method="POST">
            <input type="hidden" name="csrf_token"
                value="${req.session.csrfToken}">
            <input type="text" name="name">
            <input type="submit">
        </form>
    `);
});

app.post('/user/update', (req, res) => {
    if (!req.session.user) {
        return res.status(401).json({ error: 'Not authenticated' });
    }
    const token = req.body.csrf_token;
    if (!req.session.csrfToken ||
        !crypto.timingSafeEqual(
            Buffer.from(req.session.csrfToken),
            Buffer.from(token)
        )) {
        return res.status(403).json({ error: 'Invalid CSRF token' });
    }
    const name = req.body.name;
    user.name = name;
    user.save();
    res.json({ status: 'ok' });
});
```

For applications using session-based authentication (cookies), implement
manual CSRF validation. Generate a unique token per session using
`crypto.randomBytes`, store it in the session, and validate it on POST
using `crypto.timingSafeEqual` for constant-time comparison.
