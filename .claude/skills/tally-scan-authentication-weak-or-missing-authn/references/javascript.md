# JavaScript authentication patterns

Vulnerable-vs-safe snippets for Express and Passport.js that the
`authentication.weak_or_missing_authn` scanner recognizes.

## Express: missing auth middleware

### Vulnerable

```javascript
app.get("/api/users/:id", (req, res) => {
  const user = await User.findById(req.params.id);
  res.json(user);
});
```

### Safe

```javascript
app.get("/api/users/:id", requireAuth, (req, res) => {
  const user = await User.findById(req.params.id);
  res.json(user);
});

function requireAuth(req, res, next) {
  if (!req.user) return res.status(401).json({ error: "Unauthorized" });
  next();
}
```

## Express: missing Passport.js guard

### Vulnerable

```javascript
app.get(
  "/api/profile",
  (req, res) => {
    res.json(req.user);
  },
);
```

### Safe

```javascript
app.get(
  "/api/profile",
  passport.authenticate("jwt", { session: false }),
  (req, res) => {
    res.json(req.user);
  },
);
```

## Missing Authorization header check

### Vulnerable

```javascript
app.post("/api/orders", async (req, res) => {
  const order = await Order.create(req.body);
  res.status(201).json(order);
});
```

### Safe

```javascript
app.post("/api/orders", verifyToken, async (req, res) => {
  const order = await Order.create(req.body);
  res.status(201).json(order);
});

function verifyToken(req, res, next) {
  const authHeader = req.headers.authorization;
  if (!authHeader) {
    return res.status(401).json({ error: "Missing token" });
  }
  const token = authHeader.split(" ")[1];
  jwt.verify(token, process.env.JWT_SECRET, (err, decoded) => {
    if (err) return res.status(403).json({ error: "Invalid token" });
    req.user = decoded;
    next();
  });
}
```

## Hardcoded credentials

### Vulnerable

```javascript
app.post("/login", (req, res) => {
  if (req.body.password === "secret123") {
    res.json({ token: generateToken() });
  }
});
```

### Safe

```javascript
app.post("/login", async (req, res) => {
  const user = await User.findOne({ email: req.body.email });
  if (!user) return res.status(401).json({ error: "Invalid" });
  const valid = await bcrypt.compare(
    req.body.password,
    user.passwordHash,
  );
  if (!valid) return res.status(401).json({ error: "Invalid" });
  res.json({ token: generateToken(user) });
});
```
