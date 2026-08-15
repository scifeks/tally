# TypeScript template injection patterns

Vulnerable-vs-safe snippets for the TypeScript template engines the
`injection.template` scanner recognizes. When multiple safe forms exist,
the canonical one is shown first.

## Nunjucks (typed)

### Vulnerable

```typescript
import * as nunjucks from 'nunjucks';

// User input as template source
const userTemplate: string = req.query.template as string;
nunjucks.renderString(userTemplate, { name: userName }, (err, html) => {
  res.send(html);
});

// Dynamic file lookup
const templateName: string = req.body.template as string;
nunjucks.render(templateName, { name: userName }, (err, html) => {
  res.send(html);
});
```

### Safe

```typescript
import * as nunjucks from 'nunjucks';

// Render a literal template
const template: string = 'Hello {{ name }}!';
nunjucks.renderString(template, { name: userName }, (err, html) => {
  res.send(html);
});

// Or render from a file with hardcoded path
nunjucks.render('./views/profile.html', { name: userName }, (err, html) => {
  res.send(html);
});

// Configure a loader with restricted directories
const env = nunjucks.configure('./views', { autoescape: true });
env.render('profile.html', { name: userName }, (err, html) => {
  res.send(html);
});
```

TypeScript typing does not prevent SSTI. Keep template sources as
literals or hardcoded file paths. Pass user input through the context
object, never as the template source or filename.

## EJS (typed)

### Vulnerable

```typescript
import * as ejs from 'ejs';

// User input as template source
const userTemplate: string = req.query.template as string;
const rendered: string = ejs.render(userTemplate, { name: userName });

// Dynamic file path
const templatePath: string = req.body.path as string;
ejs.renderFile(templatePath, { data: userName }, (err, html) => {
  res.send(html || '');
});
```

### Safe

```typescript
import * as ejs from 'ejs';

// Render from a literal filename
ejs.renderFile('./views/profile.ejs', { name: userName }, (err, html) => {
  if (err) return next(err);
  res.send(html);
});

// Or render a literal template
const template: string = 'Hello <%= name %>!';
const rendered: string = ejs.render(template, { name: userName });
```

Even with TypeScript's type system, EJS does not protect against
dynamic template sources. Hardcode template filenames and pass user
data through the data object.

## Angular (client-side)

### Vulnerable

```typescript
import { Component } from '@angular/core';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';

@Component({
  selector: 'app-profile',
  template: '<div [innerHTML]="profileHtml"></div>'
})
export class ProfileComponent {
  profileHtml: SafeHtml;

  constructor(private sanitizer: DomSanitizer) {}

  loadProfile(userId: string) {
    // Dangerous: user input embedded in template markup
    const html = `<h1>Hello ${userId}!</h1>`;
    this.profileHtml = this.sanitizer.bypassSecurityTrustHtml(html);
  }
}
```

### Safe

```typescript
import { Component, OnInit } from '@angular/core';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';

@Component({
  selector: 'app-profile',
  template: '<div><h1>Hello {{ name }}!</h1></div>'
})
export class ProfileComponent implements OnInit {
  name: string = '';

  constructor(private sanitizer: DomSanitizer) {}

  loadProfile(userId: string) {
    // Safe: data binding, no HTML construction
    this.name = userId;
  }

  // Only bypass security for static, trusted HTML
  getTrustedContent(staticHtml: string): SafeHtml {
    return this.sanitizer.bypassSecurityTrustHtml(staticHtml);
  }
}
```

Angular's data binding interpolation (`{{ }}`) is safe by default.
Avoid `bypassSecurityTrustHtml()` when user input is involved. Use
property and event binding instead. If HTML must be rendered, use
an explicitly sanitized library or whitelist.

## Express + Templating (server-side)

### Vulnerable

```typescript
import express from 'express';
import * as ejs from 'ejs';

const app = express();

// User input in template path
app.get('/render', (req: express.Request, res: express.Response) => {
  const templatePath = req.query.template as string;
  ejs.renderFile(templatePath, {}, (err, html) => {
    res.send(html);
  });
});

// User input in template source
app.post('/compile', (req: express.Request, res: express.Response) => {
  const userTemplate = req.body.template as string;
  res.send(ejs.render(userTemplate, {}));
});
```

### Safe

```typescript
import express from 'express';

const app = express();
app.set('view engine', 'ejs');
app.set('views', './views');

// Express template lookup with hardcoded names
app.get('/profile/:id', (req: express.Request, res: express.Response) => {
  res.render('profile', { userId: req.params.id });
});

// Allowlist for template selection
const allowedTemplates: Record<string, boolean> = {
  'profile': true,
  'dashboard': true
};

app.get('/view/:name', (req: express.Request, res: express.Response) => {
  const templateName = req.params.name;
  if (!allowedTemplates[templateName]) {
    res.status(400).send('Invalid template');
    return;
  }
  res.render(templateName, {});
});
```

Express view rendering is safe when template names are hardcoded or
validated against an allowlist. Let the framework handle file loading.
Pass user data through the context object, not as template source.
