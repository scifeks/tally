# TypeScript file upload patterns

Vulnerable-vs-safe snippets for the TypeScript web frameworks and typed
middleware the `data_integrity.file_upload` scanner recognizes.

## NestJS + @UploadedFile

### Vulnerable

```typescript
import { Controller, Post, UploadedFile } from '@nestjs/common';
import { Express } from 'express';

@Controller('api')
export class UploadController {
    @Post('upload')
    uploadFile(@UploadedFile() file: Express.Multer.File) {
        const savePath = `./uploads/${file.originalname}`;
        // File is saved without validation
        return { success: true };
    }
}
```

### Safe

```typescript
import {
    Controller, Post, UploadedFile,
    BadRequestException, UseInterceptors,
    ParseFilePipe, FileTypeValidator, MaxFileSizeValidator
} from '@nestjs/common';
import { FileInterceptor } from '@nestjs/platform-express';
import { diskStorage } from 'multer';
import { randomBytes } from 'crypto';
import { Express } from 'express';

@Controller('api')
export class UploadController {
    @Post('upload')
    @UseInterceptors(
        FileInterceptor('file', {
            storage: diskStorage({
                destination: './uploads',
                filename: (req, file, cb) => {
                    const random = randomBytes(8).toString('hex');
                    const ext = file.originalname.split('.')
                        .pop();
                    cb(null, `${random}.${ext}`);
                }
            })
        })
    )
    uploadFile(
        @UploadedFile(
            new ParseFilePipe({
                validators: [
                    new FileTypeValidator({
                        fileType: /(jpeg|png|gif|plain|pdf)/
                    }),
                    new MaxFileSizeValidator({ maxSize: 2097152 })
                ]
            })
        )
        file: Express.Multer.File
    ) {
        return { success: true, filename: file.filename };
    }
}
```

Add `ParseFilePipe` with `FileTypeValidator` to validate MIME type and
`MaxFileSizeValidator` to cap file size. Use `diskStorage` with a custom
filename generator to prevent directory traversal. The validators run
before the endpoint handler.

## Express + multer (typed)

### Vulnerable

```typescript
import express, { Request, Response } from 'express';
import multer from 'multer';

const app = express();
const upload = multer({ dest: 'uploads/' });

app.post('/upload', upload.single('file'),
    (req: Request, res: Response) => {
        res.send('File uploaded');
    }
);
```

### Safe

```typescript
import express, { Request, Response } from 'express';
import multer, { StorageEngine } from 'multer';
import path from 'path';
import { randomBytes } from 'crypto';

const app = express();

const storage: StorageEngine = multer.diskStorage({
    destination: (req, file, cb) => {
        cb(null, 'uploads/');
    },
    filename: (req, file, cb) => {
        const timestamp = Date.now();
        const random = randomBytes(4).toString('hex');
        cb(null, `${timestamp}-${random}`);
    }
});

const fileFilter = (
    req: Request,
    file: Express.Multer.File,
    cb: multer.FileFilterCallback
) => {
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

app.post('/upload', upload.single('file'),
    (req: Request, res: Response) => {
        res.send('File uploaded');
    }
);
```

Configure a typed `fileFilter` callback that validates extension and MIME
type. Use `diskStorage` with a custom filename function to generate safe
names. Set `limits.fileSize` to cap upload size. The filter runs before
the route handler.

## Fastify + @fastify/multipart

### Vulnerable

```typescript
import Fastify, {
    FastifyInstance, FastifyRequest, FastifyReply
} from 'fastify';
import multipart from '@fastify/multipart';
import fs from 'fs/promises';

const fastify: FastifyInstance = Fastify();
await fastify.register(multipart);

fastify.post('/upload', async (
    req: FastifyRequest,
    reply: FastifyReply
) => {
    const data = await req.file();
    if (data) {
        await fs.writeFile(
            `./uploads/${data.filename}`,
            Buffer.from(await data.file.toBuffer())
        );
        return { success: true };
    }
});
```

### Safe

```typescript
import Fastify, {
    FastifyInstance, FastifyRequest, FastifyReply
} from 'fastify';
import multipart from '@fastify/multipart';
import fs from 'fs/promises';
import path from 'path';
import { randomBytes } from 'crypto';

const fastify: FastifyInstance = Fastify();
await fastify.register(multipart, {
    limits: {
        fileSize: 2 * 1024 * 1024
    }
});

const ALLOWED_EXTENSIONS = ['txt', 'pdf', 'jpg', 'png'];
const ALLOWED_MIMES = [
    'text/plain', 'application/pdf', 'image/jpeg', 'image/png'
];

fastify.post('/upload', async (
    req: FastifyRequest,
    reply: FastifyReply
) => {
    const data = await req.file();
    if (!data) {
        reply.code(400).send({ error: 'No file provided' });
        return;
    }

    const ext = path.extname(data.filename)
        .toLowerCase().substring(1);
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
        reply.code(400).send({ error: 'File type not allowed' });
        return;
    }

    const encoding = data.encoding.toLowerCase();
    if (!ALLOWED_MIMES.includes(data.mimetype)) {
        reply.code(400).send({
            error: 'File content type not allowed'
        });
        return;
    }

    const buffer = Buffer.from(await data.file.toBuffer());
    const randomName = randomBytes(8).toString('hex');
    const safeName = `${randomName}.${ext}`;
    const savePath = path.join('uploads', safeName);

    try {
        await fs.writeFile(savePath, buffer);
        reply.send({ success: true, filename: safeName });
    } catch (err) {
        reply.code(500).send({ error: 'Upload failed' });
    }
});
```

Validate the extension and MIME type on every upload. Fastify's multipart
plugin sets `data.mimetype` from the Content-Type header; verify it
against an allowlist. Generate a random safe filename to prevent directory
traversal. Set the `fileSize` limit in the plugin config.
