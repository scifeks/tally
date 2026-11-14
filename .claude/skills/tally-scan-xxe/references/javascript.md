# JavaScript XXE injection patterns

Vulnerable-vs-safe snippets for the JavaScript XML libraries the `xxe`
scanner recognizes.

## libxmljs

### Vulnerable

```javascript
const libxmljs = require('libxmljs');

const userXml = request.body.xml;
const doc = libxmljs.parseXml(userXml, { noent: true });

const userXml2 = request.query.data;
const doc2 = libxmljs.parseXml(userXml2, { noent: true });
```

### Safe

```javascript
const libxmljs = require('libxmljs');

const userXml = request.body.xml;
const doc = libxmljs.parseXml(userXml, { noent: false });

const userXml2 = request.query.data;
const doc2 = libxmljs.parseXml(userXml2);
```

Omit the `noent` option or explicitly set `{ noent: false }` to disable
entity expansion. Without the option, libxmljs defaults to safe parsing.

## xml2js

### Safe

```javascript
const xml2js = require('xml2js');

const userXml = request.body.xml;
const parser = new xml2js.Parser();
parser.parseString(userXml, (err, result) => {
  if (err) handleError(err);
  process(result);
});
```

`xml2js` does not resolve external entities by default and is safe.

## fast-xml-parser

### Safe

```javascript
const parser = require('fast-xml-parser').default;

const userXml = request.body.xml;
const result = parser.parse(userXml);

const userXml2 = request.query.data;
const result2 = parser.parse(userXml2, {
  ignoreAttributes: false,
  parseTagValue: true
});
```

`fast-xml-parser` does not support entity expansion and is safe for
untrusted XML.

## xmldom

### Safe

```javascript
const { DOMParser } = require('xmldom');

const userXml = request.body.xml;
const parser = new DOMParser();
const doc = parser.parseFromString(userXml, 'text/xml');
```

The `xmldom` package does not resolve external entities by default and is
safe for parsing untrusted XML.

## Custom XML parsing

If using a custom DOM parser or entity-resolving implementation, ensure
external entity handling is disabled:

### Vulnerable

```javascript
function customParse(userXml) {
  const result = { nodes: [] };
  const entityRegex = /<!ENTITY\s+\w+\s+SYSTEM\s+"([^"]+)"/g;
  userXml.replace(entityRegex, (match, url) => {
    const content = fetch(url);
    userXml = userXml.replace(match, content);
    return match;
  });
  return libxmljs.parseXml(userXml);
}
```

### Safe

```javascript
function customParse(userXml) {
  return libxmljs.parseXml(userXml, { noent: false });
}
```

Do not manually expand entity definitions. Use safe parsers that reject or
ignore entity declarations.

## Configuration best practices

- **Never enable entity expansion** from user input.
- **Prefer parsers that disable entities by default** (xml2js,
  fast-xml-parser, xmldom).
- **If using libxmljs**, always verify `{ noent: false }` is set when
  processing untrusted XML.
- **Validate XML schema** before parsing if the XML structure is known and
  fixed.
