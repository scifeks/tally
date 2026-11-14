# JavaScript authorization logic patterns

Vulnerable-vs-safe snippets for the Node.js and browser frameworks the
`access_control.incorrect_authz_logic` scanner recognizes. When multiple
safe forms exist, the canonical one is shown first.

## Express middleware

### Vulnerable

```javascript
// Overly broad roles array
app.delete('/users/:id', (req, res) => {
    if (req.user.role in ['user', 'admin', 'moderator']) {
        User.delete(req.params.id);
    }
});

// Negated check that over-permits
app.get('/admin', (req, res) => {
    if (req.user.role !== 'guest') {
        render_admin_panel();
    }
});

// Loose equality in role comparison
app.post('/sensitive', (req, res) => {
    if (req.user.roleId == 1) {
        perform_action();
    }
});
```

### Safe

```javascript
// Only necessary roles
const ADMIN_ROLES = ['admin'];
app.delete('/users/:id', (req, res) => {
    if (ADMIN_ROLES.includes(req.user.role)) {
        User.delete(req.params.id);
    }
});

// Positive assertion
app.get('/admin', (req, res) => {
    if (req.user.role === 'admin') {
        render_admin_panel();
    }
});

// Strict equality
const ROLE_ADMIN = 1;
app.post('/sensitive', (req, res) => {
    if (req.user.roleId === ROLE_ADMIN) {
        perform_action();
    }
});
```

Use strict equality (`===`) and define allowed roles as constants to avoid
type confusion and maintenance errors.

## JWT middleware

### Vulnerable

```javascript
// JWT payload checked without signature verification upstream
app.get('/admin', (req, res) => {
    const payload = JSON.parse(Buffer.from(
        req.headers.authorization.split('.')[1],
        'base64'
    ));
    if (payload.role === 'admin') {
        return render_admin();
    }
});

// Roles not verified from token
const token = req.headers.authorization;
const decoded = jwt.decode(token);
if (decoded.role === 'admin') {
    delete_user(req.body.user_id);
}
```

### Safe

```javascript
// JWT signature verified by middleware upstream
// Middleware verifies and decodes token
app.get('/admin', verify_jwt, (req, res) => {
    // req.user is set by middleware after verification
    if (req.user.role === 'admin') {
        return render_admin();
    }
});

// Use verified token from middleware
app.delete('/users/:id', verify_jwt, (req, res) => {
    if (req.user.role === 'admin') {
        delete_user(req.params.id);
    }
});
```

Always verify the JWT signature in a middleware before reading the payload.
Never parse and use a JWT's claims without signature verification.

## Socket.io authorization

### Vulnerable

```javascript
// Overly broad roles
io.on('connection', (socket) => {
    socket.on('delete_user', (userId) => {
        if (socket.user.role in ['admin', 'moderator', 'user']) {
            User.delete(userId);
        }
    });
});

// Negated check
io.on('connection', (socket) => {
    socket.on('admin_command', (cmd) => {
        if (socket.user.role !== 'guest') {
            execute_command(cmd);
        }
    });
});
```

### Safe

```javascript
// Only necessary roles
const DELETION_ROLES = ['admin', 'moderator'];
io.on('connection', (socket) => {
    socket.on('delete_user', (userId) => {
        if (DELETION_ROLES.includes(socket.user.role)) {
            User.delete(userId);
        }
    });
});

// Positive assertion
io.on('connection', (socket) => {
    socket.on('admin_command', (cmd) => {
        if (socket.user.role === 'admin') {
            execute_command(cmd);
        }
    });
});
```

Define role sets as constants and use positive assertions to make the
authorization intent clear.

## Custom authorization helpers

### Vulnerable

```javascript
// Always-true check
function canDelete() {
    return hasPermission('edit') || true;
}

// OR logic when AND is needed
function isEditor() {
    return user.hasRole('editor') || user.hasRole('admin');
}

// Wrong permission name
if (user.hasPermission('view_report')) {
    delete_report(reportId);
}
```

### Safe

```javascript
// Check the actual permission
function canDelete() {
    return hasPermission('delete');
}

// AND when multiple conditions must hold
function isEditor() {
    return user.hasRole('editor') && user.isActive();
}

// Check permission that matches the operation
if (user.hasPermission('delete_report')) {
    delete_report(reportId);
}
```

Name helper functions to match the operation being guarded. A helper called
`canDelete` should check delete permission, not view.
