# TypeScript PII in response patterns

Vulnerable and safe snippets for TypeScript API response handling the
`crypto.pii_in_response` scanner recognizes.

## Shared entity and response type

### Vulnerable

```typescript
interface User {
  id: number;
  name: string;
  email: string;
  ssn: string;
  passwordHash: string;
}

app.get('/users/:id', async (req, res) => {
  const user: User = await findUser(req.params.id);
  res.json(user);
});
```

### Safe

```typescript
interface UserResponse {
  id: number;
  name: string;
  email: string;
}

app.get('/users/:id', async (req, res) => {
  const user = await findUser(req.params.id);
  const response: UserResponse = {
    id: user.id,
    name: user.name,
    email: user.email,
  };
  res.json(response);
});
```

Separate the database entity type from the API response type. The
response type acts as an allowlist for fields sent to the client.
