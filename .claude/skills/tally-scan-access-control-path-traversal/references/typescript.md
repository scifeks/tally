# TypeScript path traversal patterns

Vulnerable-vs-safe snippets for the TypeScript (Node.js) file
operations and frameworks the `access_control.path_traversal` scanner
recognizes. TypeScript adds type safety over JavaScript but does not
eliminate traversal risks. When multiple safe forms exist, the
canonical one is shown first.

## fs / fs.promises

### Vulnerable

```typescript
const filename: string = req.query.file as string;
const data: Buffer = fs.readFileSync(
    path.join(__dirname, 'uploads', filename)
);
res.send(data);

const file: string = req.params.path as string;
const content: string = await fs.promises.readFile(
    path.resolve('/var/data', file),
    'utf8'
);
res.json({ content });
```

### Safe

```typescript
import { promises as fs } from 'fs';
import path from 'path';

const filename: string = req.query.file as string;
const baseDir: string = path.resolve(__dirname, 'uploads');
const filepath: string = path.resolve(baseDir, filename);
if (!filepath.startsWith(baseDir + path.sep)) {
    return res.status(403).send('Access denied');
}
const data: Buffer = fs.readFileSync(filepath);
res.send(data);

// or async
const file: string = req.params.path as string;
const baseDir: string = path.resolve('/var/data');
const filepath: string = path.resolve(baseDir, file);
if (!filepath.startsWith(baseDir + path.sep)) {
    return res.status(403).send('Access denied');
}
const content: string = await fs.readFile(filepath, 'utf8');
res.json({ content });
```

Always resolve and validate containment before accessing files,
regardless of whether using sync or async APIs.

## NestJS file uploads

### Vulnerable

```typescript
@Controller('upload')
export class UploadController {
  @Post('file')
  uploadFile(
      @UploadedFile() file: Express.Multer.File,
      @Req() req: Request
  ): object {
    const destPath = path.join('/uploads', file.originalname);
    fs.writeFileSync(destPath, file.buffer);
    return { message: 'File saved' };
  }
}
```

### Safe

```typescript
import { uuid } from 'uuidv4';

@Controller('upload')
export class UploadController {
  @Post('file')
  uploadFile(
      @UploadedFile() file: Express.Multer.File,
      @Req() req: Request
  ): object {
    const baseDir: string = path.resolve('/uploads');
    const safeFilename: string = uuid();
    const destPath: string = path.resolve(
        baseDir, safeFilename
    );
    if (!destPath.startsWith(baseDir + path.sep)) {
        throw new BadRequestException('Invalid path');
    }
    fs.writeFileSync(destPath, file.buffer);
    return { message: 'File saved' };
  }
}
```

Never use the original filename directly. Generate a safe name (UUID,
timestamp) or validate the resolved path strictly.

## Express.static with validation

### Vulnerable

```typescript
const filename: string = req.query.file as string;
app.use('/files', express.static('/public/files'));
res.sendFile(path.join('/public/files', filename));
```

### Safe

```typescript
const filename: string = req.query.file as string;
const baseDir: string = path.resolve('/public/files');
const filepath: string = path.resolve(baseDir, filename);
if (!filepath.startsWith(baseDir + path.sep)) {
    return res.status(403).send('Access denied');
}
res.sendFile(filepath);

// or
const filename: string = path.basename(
    req.query.file as string
);
res.sendFile(path.join('/public/files', filename));
```

Validate the path before calling `sendFile`.

## Typed path operations

### Vulnerable

```typescript
interface FileRequest {
  directory: string;
  filename: string;
}

const getFile = (req: FileRequest): string => {
  return fs.readFileSync(
      path.join(req.directory, req.filename),
      'utf8'
  );
};

const result = getFile({
  directory: '/app/data',
  filename: req.body.file,
});
```

### Safe

```typescript
interface FileRequest {
  directory: string;
  filename: string;
}

const getFile = (req: FileRequest): string => {
  const baseDir: string = path.resolve(req.directory);
  const filepath: string = path.resolve(baseDir, req.filename);
  if (!filepath.startsWith(baseDir + path.sep)) {
      throw new Error('Path traversal detected');
  }
  return fs.readFileSync(filepath, 'utf8');
};

const result = getFile({
  directory: '/app/data',
  filename: req.body.file,
});
```

Type safety does not prevent traversal. Always validate paths at
runtime.

## Common safe patterns

For most Node.js file operations in TypeScript:

```typescript
const baseDir: string = path.resolve('/safe/base');
const userInput: string = req.params.file as string;
const filepath: string = path.resolve(baseDir, userInput);

// Check containment
if (!filepath.startsWith(baseDir + path.sep)) {
    throw new Error('Access denied');
}

// Now use filepath safely
```

Or use UUIDs for uploaded filenames and store the mapping in a
database.
