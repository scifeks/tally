# JavaScript LDAP injection patterns

Vulnerable-vs-safe snippets for the JavaScript LDAP libraries the
`injection.ldap` scanner recognizes. When multiple safe forms exist,
the canonical one is shown first.

## ldapjs

### Vulnerable

```javascript
const ldap = require('ldapjs');
const client = ldap.createClient({
  url: 'ldap://ldap.example.com',
});

const userId = req.query.uid;
client.search('dc=example,dc=com', {
  filter: `(uid=${userId})`,
}, (err, res) => {
  // ...
});
```

```javascript
const email = req.body.email;
const filter = '(mail=' + email + ')';
client.search(base, { filter }, callback);
```

### Safe

```javascript
const ldap = require('ldapjs');
const client = ldap.createClient({
  url: 'ldap://ldap.example.com',
});

const userId = req.query.uid;
const escapedUserId = ldapjs.escape(userId);
client.search('dc=example,dc=com', {
  filter: `(uid=${escapedUserId})`,
}, (err, res) => {
  // ...
});
```

```javascript
const email = req.body.email;
const escapedEmail = ldapjs.escape(email);
const filter = '(mail=' + escapedEmail + ')';
client.search(base, { filter }, callback);
```

`ldapjs` provides `ldapjs.escape()` to escape special LDAP filter characters.
Always escape request-derived values before building the filter string. Apply
it to each component before interpolation or concatenation.

## Using filter builder objects (ldapjs)

For more complex filters, consider using a filter-building abstraction:

```javascript
const ldapjs = require('ldapjs');
const filters = require('ldapjs/lib/filters');

const userId = req.query.uid;

// Using a filter builder approach (library-specific)
const filter = new ldapjs.EqualityFilter({
  attribute: 'uid',
  value: userId,
});

client.search(base, { filter }, callback);
```

Check your LDAP library for a filter builder API. Many escape values
automatically when you pass them as data (not format strings).

## Complex filters with logical operators

### Vulnerable

```javascript
const uid = req.query.uid;
const mail = req.query.mail;
const filter = `(&(uid=${uid})(mail=${mail}))`;
client.search(base, { filter }, callback);
```

### Safe

```javascript
const uid = req.query.uid;
const mail = req.query.mail;
const escapedUid = ldapjs.escape(uid);
const escapedMail = ldapjs.escape(mail);
const filter = `(&(uid=${escapedUid})(mail=${escapedMail}))`;
client.search(base, { filter }, callback);
```

Escape every variable component, even in complex filters with AND (`&`),
OR (`|`), and NOT (`!`) operators.
