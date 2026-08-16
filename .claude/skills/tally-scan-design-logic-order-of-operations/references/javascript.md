# JavaScript order-of-operations patterns

Vulnerable-vs-safe snippets for Node.js frameworks that the
`design_logic.order_of_operations` scanner recognizes.

## Express middleware chain ordering

### Vulnerable

```javascript
app.use(checkPermission);
app.use(authenticate);
app.get('/admin', (req, res) => {
  res.json({ message: 'Welcome admin' });
});
```

Express executes middleware in registration order. `checkPermission`
runs before `authenticate`. An unauthenticated user reaches the
permission check.

### Safe

```javascript
app.use(authenticate);
app.use(checkPermission);
app.get('/admin', (req, res) => {
  res.json({ message: 'Welcome admin' });
});
```

Middleware executes in registration order: `authenticate` first, then
`checkPermission`. The user is authenticated before permission is
checked.

Alternatively, apply middleware to specific routes:

```javascript
app.get('/admin',
  authenticate,
  checkPermission,
  (req, res) => {
    res.json({ message: 'Welcome admin' });
  }
);
```

## Database save before validation

### Vulnerable

```javascript
app.post('/users', async (req, res) => {
  const user = new User({ email: req.body.email });
  await user.save();
  
  const schema = Joi.object({
    email: Joi.string().email().required(),
  });
  
  const { error } = schema.validate(req.body);
  if (error) {
    throw new Error('Invalid email');
  }
  
  res.json(user);
});
```

The user is saved to the database before validation. Invalid data is
persisted.

### Safe

```javascript
app.post('/users', async (req, res) => {
  const schema = Joi.object({
    email: Joi.string().email().required(),
  });
  
  const { error, value } = schema.validate(req.body);
  if (error) {
    return res.status(400).json({ error: error.message });
  }
  
  const user = new User(value);
  await user.save();
  
  res.json(user);
});
```

Validation runs before persistence. Only valid data reaches the
database.

## Async authorization before response

### Vulnerable

```javascript
app.get('/data', async (req, res) => {
  const data = await fetchSensitiveData();
  res.json(data);
  
  const isAuthorized = await checkAuthorization(req.user);
  if (!isAuthorized) {
    res.status(403).json({ error: 'Forbidden' });
  }
});
```

This is a race condition: the response is sent before the authorization
check completes. The data leaks to the client.

### Safe

```javascript
app.get('/data', async (req, res) => {
  const isAuthorized = await checkAuthorization(req.user);
  if (!isAuthorized) {
    return res.status(403).json({ error: 'Forbidden' });
  }
  
  const data = await fetchSensitiveData();
  res.json(data);
});
```

Authorization check runs before fetching and sending data. Only
authorized users receive sensitive data.

Alternatively, use middleware to guard the route:

```javascript
async function authMiddleware(req, res, next) {
  const isAuthorized = await checkAuthorization(req.user);
  if (!isAuthorized) {
    return res.status(403).json({ error: 'Forbidden' });
  }
  next();
}

app.get('/data', authMiddleware, async (req, res) => {
  const data = await fetchSensitiveData();
  res.json(data);
});
```

## DOM sanitization before rendering

### Vulnerable

```javascript
function displayComment(commentText) {
  const elem = document.getElementById('comments');
  elem.innerHTML = `<p>${commentText}</p>`;
  
  const sanitized = DOMPurify.sanitize(commentText);
}
```

The comment is rendered before sanitization. XSS executes before
`DOMPurify` runs.

### Safe

```javascript
function displayComment(commentText) {
  const sanitized = DOMPurify.sanitize(commentText);
  const elem = document.getElementById('comments');
  elem.innerHTML = `<p>${sanitized}</p>`;
}
```

Sanitization runs before rendering. Only safe HTML reaches the DOM.

Alternatively, use text content instead of HTML:

```javascript
function displayComment(commentText) {
  const elem = document.getElementById('comments');
  const pTag = document.createElement('p');
  pTag.textContent = commentText;
  elem.appendChild(pTag);
}
```

`textContent` does not parse HTML; the browser treats it as plain text.

## Koa middleware stack ordering

### Vulnerable

```javascript
app.use(async (ctx, next) => {
  if (!ctx.state.authorized) {
    ctx.status = 403;
    ctx.body = 'Forbidden';
  } else {
    await next();
  }
});

app.use(async (ctx, next) => {
  ctx.state.authorized = await checkAuthorization(ctx);
  await next();
});

app.get('/admin', (ctx) => {
  ctx.body = { message: 'Admin panel' };
});
```

Koa middleware executes in registration order. The authorization check
runs after the permission check. An unauthenticated request bypasses
authorization.

### Safe

```javascript
app.use(async (ctx, next) => {
  ctx.state.authorized = await checkAuthorization(ctx);
  await next();
});

app.use(async (ctx, next) => {
  if (!ctx.state.authorized) {
    ctx.status = 403;
    ctx.body = 'Forbidden';
  } else {
    await next();
  }
});

app.get('/admin', (ctx) => {
  ctx.body = { message: 'Admin panel' };
});
```

Middleware executes in order: authorization check first, permission
enforcement second.

## Fastify hook ordering

### Vulnerable

```javascript
fastify.addHook('preHandler', async (request, reply) => {
  if (!request.user.isAdmin) {
    reply.code(403).send({ error: 'Forbidden' });
  }
});

fastify.addHook('onRequest', async (request, reply) => {
  request.user = await authenticate(request);
});

fastify.get('/admin', (request, reply) => {
  reply.send({ message: 'Admin' });
});
```

Fastify executes `onRequest` hooks first, then `preHandler` hooks.
Authentication runs after the admin check. An unauthenticated request
bypasses the role check.

### Safe

```javascript
fastify.addHook('onRequest', async (request, reply) => {
  request.user = await authenticate(request);
});

fastify.addHook('preHandler', async (request, reply) => {
  if (!request.user || !request.user.isAdmin) {
    reply.code(403).send({ error: 'Forbidden' });
  }
});

fastify.get('/admin', (request, reply) => {
  reply.send({ message: 'Admin' });
});
```

Hooks execute in documented order: `onRequest` first (authentication),
then `preHandler` (authorization).
