# TypeScript LDAP injection patterns

Vulnerable-vs-safe snippets for the TypeScript LDAP libraries the
`injection.ldap` scanner recognizes. TypeScript wraps JavaScript
libraries with type annotations; the injection patterns are identical.
When multiple safe forms exist, the canonical one is shown first.

## ldapjs with TypeScript bindings

### Vulnerable

```typescript
import * as ldap from 'ldapjs';

const client = ldap.createClient({
  url: 'ldap://ldap.example.com',
});

const userId: string = req.query.uid;
client.search('dc=example,dc=com', {
  filter: `(uid=${userId})`,
}, (err: Error | null, res: any) => {
  // ...
});
```

```typescript
const email: string = req.body.email;
const filter: string = '(mail=' + email + ')';
client.search(base, { filter }, callback);
```

### Safe

```typescript
import * as ldap from 'ldapjs';

const client = ldap.createClient({
  url: 'ldap://ldap.example.com',
});

const userId: string = req.query.uid;
const escapedUserId: string = ldap.escape(userId);
client.search('dc=example,dc=com', {
  filter: `(uid=${escapedUserId})`,
}, (err: Error | null, res: any) => {
  // ...
});
```

```typescript
const email: string = req.body.email;
const escapedEmail: string = ldap.escape(email);
const filter: string = '(mail=' + escapedEmail + ')';
client.search(base, { filter }, callback);
```

`ldapjs.escape()` escapes special LDAP filter characters. Always apply it to
request-derived values before interpolation or concatenation, even with
TypeScript type safety in place. Type annotations do not prevent injection.

## Using typed filter builders

For complex filters with type-safe construction:

```typescript
import * as ldap from 'ldapjs';

const userId: string = req.query.uid;

// Check your LDAP library for a typed filter builder
const filter: ldap.Filter = new ldap.EqualityFilter({
  attribute: 'uid',
  value: userId,
});

client.search(base, { filter }, callback);
```

Many LDAP libraries offer typed filter-builder APIs that escape values
automatically. Prefer these over string interpolation.

## Complex typed filters

### Vulnerable

```typescript
const uid: string = req.query.uid;
const mail: string = req.query.mail;
const filter: string = `(&(uid=${uid})(mail=${mail}))`;
client.search(base, { filter }, callback);
```

### Safe

```typescript
const uid: string = req.query.uid;
const mail: string = req.query.mail;
const escapedUid: string = ldap.escape(uid);
const escapedMail: string = ldap.escape(mail);
const filter: string = `(&(uid=${escapedUid})(mail=${escapedMail}))`;
client.search(base, { filter }, callback);
```

Escape every variable component in complex filters, even when type-checking
passes. Type safety and input safety are orthogonal concerns.
