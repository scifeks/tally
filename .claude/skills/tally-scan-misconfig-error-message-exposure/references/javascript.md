# JavaScript error message exposure patterns

Vulnerable-vs-safe snippets for Node.js error handling the
`misconfig.error_message_exposure` scanner recognizes. When multiple safe
forms exist, the canonical one is shown first.

## Express error middleware

### Vulnerable

```javascript
app.use((err, req, res, next) => {
    res.status(500).json({
        error: err.message,
        stack: err.stack
    });
});

app.get('/data', (req, res) => {
    try {
        const data = fetchData();
        res.json(data);
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});
```

### Safe

```javascript
const logger = require('pino')();

app.use((err, req, res, next) => {
    logger.error(err, "Unhandled error");
    res.status(500).json({
        error: "Internal server error"
    });
});

app.get('/data', (req, res) => {
    try {
        const data = fetchData();
        res.json(data);
    } catch (err) {
        logger.error(err, "Error fetching data");
        res.status(500).json({
            error: "Internal server error"
        });
    }
});
```

Log exceptions server-side using a logger like Pino or Winston. Return a
generic error message in the response without exposing exception details
or stack traces.

## Koa error handling

### Vulnerable

```javascript
app.use(async (ctx, next) => {
    try {
        await next();
    } catch (err) {
        ctx.status = 500;
        ctx.body = { error: err.message, stack: err.stack };
    }
});

router.get('/data', async (ctx) => {
    try {
        ctx.body = await fetchData();
    } catch (err) {
        ctx.status = 500;
        ctx.body = { error: err.message };
    }
});
```

### Safe

```javascript
const logger = require('pino')();

app.use(async (ctx, next) => {
    try {
        await next();
    } catch (err) {
        logger.error(err, "Unhandled error");
        ctx.status = 500;
        ctx.body = { error: "Internal server error" };
    }
});

router.get('/data', async (ctx) => {
    try {
        ctx.body = await fetchData();
    } catch (err) {
        logger.error(err, "Error fetching data");
        ctx.status = 500;
        ctx.body = { error: "Internal server error" };
    }
});
```

Log the exception server-side. Return a generic error message without
exposing the exception message or stack trace.

## Fastify error handlers

### Vulnerable

```javascript
fastify.setErrorHandler((error, request, reply) => {
    reply.status(500).send({
        error: error.message,
        trace: error.stack
    });
});

fastify.get('/data', async (request, reply) => {
    try {
        return await fetchData();
    } catch (err) {
        return reply.status(500).send({
            error: err.message
        });
    }
});
```

### Safe

```javascript
const logger = require('pino')();

fastify.setErrorHandler((error, request, reply) => {
    logger.error(error, "Unhandled error");
    reply.status(500).send({
        error: "Internal server error"
    });
});

fastify.get('/data', async (request, reply) => {
    try {
        return await fetchData();
    } catch (err) {
        logger.error(err, "Error fetching data");
        return reply.status(500).send({
            error: "Internal server error"
        });
    }
});
```

Log errors server-side using a logger. Return a generic error message
without exposing the exception message or stack trace.

## Bare catch blocks

### Vulnerable

```javascript
app.post('/process', (req, res) => {
    try {
        const result = process(req.body);
        res.json(result);
    } catch (e) {
        res.status(400).json({ error: e.toString() });
    }
});
```

### Safe

```javascript
const logger = require('pino')();

app.post('/process', (req, res) => {
    try {
        const result = process(req.body);
        res.json(result);
    } catch (e) {
        logger.error(e, "Error processing request");
        res.status(400).json({ error: "Invalid request" });
    }
});
```

Log the exception server-side with a logger. Return a generic error message
that describes what failed (e.g., "Invalid request") without exposing the
exception message or stack.
