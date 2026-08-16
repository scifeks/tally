# JavaScript template injection patterns

Vulnerable-vs-safe snippets for the JavaScript template engines the
`injection.template` scanner recognizes. When multiple safe forms exist,
the canonical one is shown first.

## EJS

### Vulnerable

```javascript
const ejs = require('ejs');

// Direct render with user input as template
const userTemplate = req.query.template;
const rendered = ejs.render(userTemplate, { name: userName });

// Or renderFile with dynamic path
const templatePath = req.body.template;
ejs.renderFile(templatePath, data, (err, html) => {
  res.send(html);
});
```

### Safe

```javascript
const ejs = require('ejs');

// Render from a literal filename
ejs.renderFile('./views/profile.ejs', { name: userName }, (err, html) => {
  if (err) return next(err);
  res.send(html);
});

// Or render a literal template with data
const template = 'Hello <%= name %>!';
const rendered = ejs.render(template, { name: userName });
```

EJS templates should always be loaded from files. Pass user input
through the `data` parameter, not as the template source. Hardcode
template filenames.

## Pug (formerly Jade)

### Vulnerable

```javascript
const pug = require('pug');

// User input as template source
const userTemplate = req.query.template;
const html = pug.render(userTemplate, { name: userName });

// Dynamic file path
const templatePath = req.body.view;
const html = pug.renderFile(templatePath, { name: userName });
```

### Safe

```javascript
const pug = require('pug');

// Render from a literal filename
const html = pug.renderFile('./views/profile.pug', {
  name: userName
});

// Or compile a literal template
const template = pug.compile('p= name');
const html = template({ name: userName });
```

Pug templates should be loaded from files. Pass user data through
the options/context object. Do not pass user input as the template
source or file path.

## Handlebars

### Vulnerable

```javascript
const Handlebars = require('handlebars');

// User input compiled as template
const userTemplate = req.query.template;
const template = Handlebars.compile(userTemplate);
const html = template({ name: userName });

// Or registered helper with unsafe code
Handlebars.registerHelper('unsafe', (input) => {
  return new Handlebars.SafeString(input);
});
const template = Handlebars.compile('{{unsafe userInput}}');
```

### Safe

```javascript
const Handlebars = require('handlebars');

// Literal template string
const template = Handlebars.compile('Hello {{name}}!');
const html = template({ name: userName });

// Or from a file
const fs = require('fs');
const templateSource = fs.readFileSync('./views/profile.hbs', 'utf8');
const template = Handlebars.compile(templateSource);
const html = template({ name: userName });
```

Handlebars templates should be defined as literal strings or loaded
from files. Never compile user input. Register helpers only for
trusted operations. User data goes through the context, not the
template source.

## Nunjucks

### Vulnerable

```javascript
const nunjucks = require('nunjucks');

// User input as template source
const userTemplate = req.query.template;
nunjucks.renderString(userTemplate, { name: userName }, (err, html) => {
  res.send(html);
});

// Or dynamic file lookup
const templateName = req.body.template;
nunjucks.render(templateName, { name: userName }, (err, html) => {
  res.send(html);
});
```

### Safe

```javascript
const nunjucks = require('nunjucks');

// Render a literal template
nunjucks.renderString('Hello {{ name }}!', { name: userName }, (err, html) => {
  res.send(html);
});

// Or render from a file
nunjucks.render('./views/profile.html', { name: userName }, (err, html) => {
  res.send(html);
});
```

Nunjucks should render literal templates or load from files with
hardcoded paths. Pass user input through the data object, never as
the template source or filename. Set up a loader with an explicit
template directory.
