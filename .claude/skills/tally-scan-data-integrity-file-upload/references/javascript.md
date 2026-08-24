# JavaScript file upload patterns

Vulnerable-vs-safe snippets for the Node.js web frameworks and middleware
the `data_integrity.file_upload` scanner recognizes.

## Express + multer

### Vulnerable

```javascript
const express = require('express');
const multer = require('multer');
const app = express();

const upload = multer({ dest: 'uploads/' });

app.post('/upload', upload.single('file'), (req, res) => {
    res.send('File uploaded');
});
```

### Safe

```javascript
const express = require('express');
const multer = require('multer');
const path = require('path');
const app = express();

const storage = multer.diskStorage({
    destination: (req, file, cb) => {
        cb(null, 'uploads/');
    },
    filename: (req, file, cb) => {
        const timestamp = Date.now();
        const random = Math.random().toString(36).substring(2, 8);
        cb(null, timestamp + '-' + random);
    }
});

const fileFilter = (req, file, cb) => {
    const allowed = ['jpg', 'jpeg', 'png', 'gif', 'txt'];
    const allowedMimes = [
        'image/jpeg', 'image/png', 'image/gif', 'text/plain'
    ];

    const ext = path.extname(file.originalname)
        .toLowerCase().substring(1);
    if (!allowed.includes(ext)) {
        return cb(new Error('File type not allowed'));
    }

    if (!allowedMimes.includes(file.mimetype)) {
        return cb(new Error('File content type not allowed'));
    }

    cb(null, true);
};

const upload = multer({
    storage,
    fileFilter,
    limits: { fileSize: 2 * 1024 * 1024 }
});

app.post('/upload', upload.single('file'), (req, res) => {
    res.send('File uploaded');
});
```

Configure a `fileFilter` callback that validates the extension and MIME
type against an allowlist. Use `diskStorage` with a custom `filename`
function to generate safe filenames. Set `limits.fileSize` to cap the
upload size.

## Express + express-fileupload

### Vulnerable

```javascript
const express = require('express');
const fileUpload = require('express-fileupload');
const app = express();

app.use(fileUpload());

app.post('/upload', (req, res) => {
    const file = req.files.document;
    file.mv('uploads/' + file.name);
    res.send('File uploaded');
});
```

### Safe

```javascript
const express = require('express');
const fileUpload = require('express-fileupload');
const path = require('path');
const crypto = require('crypto');
const app = express();

app.use(fileUpload());

const ALLOWED_EXTENSIONS = ['txt', 'pdf', 'jpg', 'png'];
const ALLOWED_MIMES = [
    'text/plain', 'application/pdf', 'image/jpeg', 'image/png'
];

app.post('/upload', (req, res) => {
    const file = req.files.document;
    const ext = path.extname(file.name).toLowerCase().substring(1);

    if (!ALLOWED_EXTENSIONS.includes(ext)) {
        return res.status(400).send('File type not allowed');
    }

    if (!ALLOWED_MIMES.includes(file.mimetype)) {
        return res.status(400).send('File content type not allowed');
    }

    const randomName = crypto.randomBytes(16).toString('hex');
    const safeName = randomName + '.' + ext;
    const uploadPath = path.join('uploads', safeName);

    file.mv(uploadPath, (err) => {
        if (err) {
            return res.status(500).send(err);
        }
        res.send('File uploaded');
    });
});
```

Always validate the extension and MIME type before calling `.mv()`. Use
`path.extname()` to extract the extension and check it against an
allowlist. Generate a random safe filename to prevent directory traversal
and filename collisions.

## Koa + koa-body or formidable

### Vulnerable

```javascript
const Koa = require('koa');
const body = require('koa-body');
const app = new Koa();

app.use(body({ multipart: true }));

app.use(async (ctx) => {
    const file = ctx.request.files.upload;
    if (file) {
        const fs = require('fs');
        const path = require('path');
        const newPath = path.join('uploads', file.name);
        fs.renameSync(file.path, newPath);
        ctx.body = 'File uploaded';
    }
});
```

### Safe

```javascript
const Koa = require('koa');
const body = require('koa-body');
const fs = require('fs').promises;
const path = require('path');
const crypto = require('crypto');
const app = new Koa();

const ALLOWED_EXTENSIONS = ['txt', 'pdf', 'jpg', 'png'];
const ALLOWED_MIMES = [
    'text/plain', 'application/pdf', 'image/jpeg', 'image/png'
];

app.use(body({ multipart: true }));

app.use(async (ctx) => {
    const file = ctx.request.files.upload;
    if (!file) {
        ctx.status = 400;
        ctx.body = 'No file provided';
        return;
    }

    const ext = path.extname(file.name)
        .toLowerCase().substring(1);
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
        ctx.status = 400;
        ctx.body = 'File type not allowed';
        return;
    }

    if (!ALLOWED_MIMES.includes(file.type)) {
        ctx.status = 400;
        ctx.body = 'File content type not allowed';
        return;
    }

    const randomName = crypto.randomBytes(16).toString('hex');
    const safeName = randomName + '.' + ext;
    const newPath = path.join('uploads', safeName);

    try {
        await fs.rename(file.path, newPath);
        ctx.body = 'File uploaded';
    } catch (err) {
        ctx.status = 500;
        ctx.body = 'Upload failed';
    }
});
```

Validate the extension against an allowlist before moving the file.
Check the `type` property against MIME allowlist. Generate a random safe
filename to prevent directory traversal and collisions.
