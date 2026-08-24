# JavaScript session management patterns

Vulnerable-vs-safe snippets for Express session handling that the
`authentication.session_management` scanner recognizes.

## Express: session fixation

### Vulnerable

```javascript
app.post("/login", (req, res) => {
  const user = authenticate(req.body.username, req.body.password);
  if (user) {
    req.session.userId = user.id;
    res.redirect("/dashboard");
  }
});
```

### Safe

```javascript
app.post("/login", (req, res) => {
  const user = authenticate(req.body.username, req.body.password);
  if (user) {
    req.session.regenerate((err) => {
      if (err) return res.status(500).send("Session error");
      req.session.userId = user.id;
      res.redirect("/dashboard");
    });
  }
});
```

`req.session.regenerate()` destroys the old session and creates a
new one. Set session data inside the callback, after the new
session is established.

## Express: insecure cookie flags

### Vulnerable

```javascript
app.use(
  session({
    secret: process.env.SESSION_SECRET,
    resave: false,
    saveUninitialized: false,
  })
);
```

### Safe

```javascript
app.use(
  session({
    secret: process.env.SESSION_SECRET,
    resave: false,
    saveUninitialized: false,
    cookie: {
      secure: true,
      httpOnly: true,
      sameSite: "lax",
      maxAge: 3600000,
    },
  })
);
```

Omitting the `cookie` options leaves all flags at their defaults.
`secure` defaults to `false`; `httpOnly` defaults to `true` in
`express-session` but relying on the default is fragile.

## Express: missing session expiry

### Vulnerable

```javascript
app.use(
  session({
    secret: process.env.SESSION_SECRET,
    cookie: {
      secure: true,
      httpOnly: true,
    },
  })
);
```

### Safe

```javascript
app.use(
  session({
    secret: process.env.SESSION_SECRET,
    cookie: {
      secure: true,
      httpOnly: true,
      maxAge: 3600000,
    },
  })
);
```

Without `maxAge`, the cookie is a session cookie (deleted when the
browser closes), but the server-side session persists in the store
indefinitely. Set `maxAge` to bound the session lifetime.

## Express: MemoryStore in production

### Vulnerable

```javascript
app.use(
  session({
    secret: process.env.SESSION_SECRET,
    resave: false,
    saveUninitialized: false,
  })
);
```

### Safe

```javascript
const RedisStore = require("connect-redis").default;
const redis = require("redis");
const client = redis.createClient();

app.use(
  session({
    store: new RedisStore({ client }),
    secret: process.env.SESSION_SECRET,
    resave: false,
    saveUninitialized: false,
  })
);
```

The default MemoryStore leaks memory under load and loses all
sessions on process restart. Use a persistent store (Redis,
MongoDB, PostgreSQL) in production.
