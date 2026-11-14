# JavaScript open redirect patterns

Vulnerable-vs-safe snippets for Node.js web frameworks the
`access_control.open_redirect` scanner recognizes. TypeScript-specific
patterns live in `typescript.md`.

## Express

### Vulnerable

```javascript
app.get('/login', (req, res) => {
    const next = req.query.url;
    res.redirect(next);
});

app.post('/auth', (req, res) => {
    res.redirect(req.body.returnUrl);
});
```

### Safe

```javascript
const ALLOWED_HOSTS = ['example.com', 'app.example.com'];

function isAllowedRedirect(url) {
    try {
        const parsed = new URL(url);
        return ALLOWED_HOSTS.includes(parsed.hostname);
    } catch (e) {
        return false;
    }
}

app.get('/login', (req, res) => {
    const next = req.query.url;
    if (next && isAllowedRedirect(next)) {
        res.redirect(next);
    } else {
        res.redirect('/dashboard');
    }
});

app.post('/auth', (req, res) => {
    const url = req.body.returnUrl;
    if (url && url.startsWith('/')) {
        res.redirect(url);
    } else {
        res.redirect('/dashboard');
    }
});
```

Use `new URL()` to parse the destination and check its `hostname`
property against an allowlist. For same-origin redirects, check
that the URL starts with `/` and contains no host.

## Manual Location header

### Vulnerable

```javascript
app.get('/go', (req, res) => {
    const target = req.query.next;
    res.set('Location', target).status(302).end();
});
```

### Safe

```javascript
const ALLOWED_HOSTS = ['example.com'];

app.get('/go', (req, res) => {
    const target = req.query.next;
    try {
        const parsed = new URL(target);
        if (ALLOWED_HOSTS.includes(parsed.hostname)) {
            res.set('Location', target).status(302).end();
        } else {
            res.set('Location', '/dashboard').status(302).end();
        }
    } catch (e) {
        res.set('Location', '/dashboard').status(302).end();
    }
});
```

Validate the URL before setting the Location header. Handle `URL`
constructor exceptions (thrown when the URL string is invalid).

## Relative-path-only redirect (safe)

```javascript
app.get('/navigate', (req, res) => {
    const page = req.query.page || 'home';
    const allowed = ['home', 'about', 'contact'];

    if (!allowed.includes(page)) {
        return res.redirect('/');
    }

    res.redirect(`/${page}`);
});
```

Relative paths that do not include a domain are inherently same-origin
and safe, provided the path segment is validated.

## Anti-pattern: parsing without checking the result

```javascript
app.get('/login', (req, res) => {
    const url = req.query.next;
    try {
        new URL(url);
    } catch (e) {
        // Log the error, do nothing
    }
    res.redirect(url);
});
```

The URL is parsed but the exception is caught and the redirect
proceeds anyway. Always validate the result and only redirect if
the URL is safe.
