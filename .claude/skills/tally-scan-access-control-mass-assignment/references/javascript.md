# JavaScript mass assignment patterns

Vulnerable-vs-safe snippets for the Node.js ORMs and frameworks the
`access_control.mass_assignment` scanner recognizes.

## Sequelize with create

### Vulnerable

```javascript
const express = require('express');
const { User } = require('./models');

app.post('/users', async (req, res) => {
  const user = await User.create(req.body);
  res.json(user);
});

app.put('/users/:id', async (req, res) => {
  const user = await User.findByPk(req.params.id);
  await user.update(req.body);
  res.json(user);
});
```

An attacker can set any column: `is_admin`, `role`, `balance`, etc.

### Safe

```javascript
const express = require('express');
const { User } = require('./models');

app.post('/users', async (req, res) => {
  const user = await User.create(
    {
      username: req.body.username,
      email: req.body.email,
      password: req.body.password,
    },
    { fields: ['username', 'email', 'password'] },
  );
  res.json(user);
});

app.put('/users/:id', async (req, res) => {
  const user = await User.findByPk(req.params.id);
  await user.update(
    {
      email: req.body.email,
      username: req.body.username,
    },
    { fields: ['email', 'username'] },
  );
  res.json(user);
});
```

Use the `fields` option to whitelist which columns can be updated.
Alternatively, construct a filtered object:

```javascript
const allowedFields = ['username', 'email'];
const filtered = {};
for (const key of allowedFields) {
  if (key in req.body) {
    filtered[key] = req.body[key];
  }
}
const user = await User.create(filtered);
```

## Mongoose with direct assignment

### Vulnerable

```javascript
const express = require('express');
const User = require('./models/User');

app.post('/users', async (req, res) => {
  const user = new User(req.body);
  await user.save();
  res.json(user);
});

app.put('/users/:id', async (req, res) => {
  const user = await User.findByIdAndUpdate(
    req.params.id,
    req.body,
    { new: true },
  );
  res.json(user);
});
```

Any field in `req.body` is assigned to the Mongoose document.

### Safe

```javascript
const express = require('express');
const User = require('./models/User');

app.post('/users', async (req, res) => {
  const user = new User({
    username: req.body.username,
    email: req.body.email,
    password: req.body.password,
  });
  await user.save();
  res.json(user);
});

app.put('/users/:id', async (req, res) => {
  const user = await User.findById(req.params.id);
  if (req.body.email) user.email = req.body.email;
  if (req.body.username) user.username = req.body.username;
  await user.save();
  res.json(user);
});
```

Explicitly select which fields to assign from the request. Alternatively,
define allowed fields and filter:

```javascript
const allowedFields = ['email', 'username'];
const update = {};
for (const field of allowedFields) {
  if (field in req.body) {
    update[field] = req.body[field];
  }
}
await User.findByIdAndUpdate(req.params.id, update);
```

## Express with direct object iteration

### Vulnerable

```javascript
app.post('/users', async (req, res) => {
  const user = new User();
  for (const key in req.body) {
    user[key] = req.body[key];
  }
  await user.save();
  res.json(user);
});
```

Every key in `req.body` becomes a property on the user object.

### Safe

```javascript
app.post('/users', async (req, res) => {
  const allowedFields = ['name', 'email', 'phone'];
  const user = new User();

  for (const field of allowedFields) {
    if (field in req.body) {
      user[field] = req.body[field];
    }
  }
  await user.save();
  res.json(user);
});
```

Maintain an allowlist of permitted field names and only iterate over
fields in that list.

## TypeORM save without field filtering

### Vulnerable

```javascript
import { getRepository } from 'typeorm';
import { User } from './entity/User';

app.post('/users', async (req, res) => {
  const userRepository = getRepository(User);
  const user = userRepository.create(req.body);
  await userRepository.save(user);
  res.json(user);
});
```

The `.create()` method assigns all properties from `req.body`.

### Safe

```javascript
import { getRepository } from 'typeorm';
import { User } from './entity/User';

app.post('/users', async (req, res) => {
  const userRepository = getRepository(User);
  const user = userRepository.create({
    username: req.body.username,
    email: req.body.email,
    password: req.body.password,
  });
  await userRepository.save(user);
  res.json(user);
});
```

Explicitly select which properties from the request are passed to
`.create()`.
