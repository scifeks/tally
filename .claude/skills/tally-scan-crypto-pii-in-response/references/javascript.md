# JavaScript PII in response patterns

Vulnerable and safe snippets for Node.js API response handling the
`crypto.pii_in_response` scanner recognizes.

## Express res.json with full object

### Vulnerable

```javascript
app.get('/users/:id', async (req, res) => {
  const user = await User.findById(req.params.id);
  res.json(user);
});
```

### Safe

```javascript
app.get('/users/:id', async (req, res) => {
  const user = await User.findById(req.params.id);
  const { id, name, email } = user;
  res.json({ id, name, email });
});
```

Destructure only the fields the client needs. Database objects often
contain `password_hash`, `ssn`, `token`, and other sensitive fields.

## GraphQL resolver

### Vulnerable

```javascript
const resolvers = {
  Query: {
    user: (_, { id }) => User.findById(id),
  },
};
```

### Safe

```javascript
const resolvers = {
  Query: {
    user: async (_, { id }) => {
      const user = await User.findById(id);
      return {
        id: user.id,
        name: user.name,
        email: user.email,
      };
    },
  },
};
```

Even when the GraphQL schema restricts visible fields, the resolver
should not return the full database object. Field-level resolvers with
authorization checks are preferred for sensitive data.
