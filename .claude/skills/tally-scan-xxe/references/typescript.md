# TypeScript XXE injection patterns

Vulnerable-vs-safe snippets for TypeScript XML libraries and bindings the
`xxe` scanner recognizes. TypeScript bindings to JavaScript libraries carry
the same XXE risks as the underlying JavaScript code.

## libxmljs with TypeScript

### Vulnerable

```typescript
import * as libxmljs from 'libxmljs';

const userXml: string = request.body.xml;
const doc: libxmljs.Document = libxmljs.parseXml(userXml,
  { noent: true }
);
```

### Safe

```typescript
import * as libxmljs from 'libxmljs';

const userXml: string = request.body.xml;
const doc: libxmljs.Document = libxmljs.parseXml(userXml,
  { noent: false }
);
```

TypeScript type annotations do not enforce XXE safety. The underlying
libxmljs behavior is the same as JavaScript; set `{ noent: false }` or omit
the option to disable entity expansion.

## xml2js with TypeScript

### Safe

```typescript
import { Parser } from 'xml2js';

const userXml: string = request.body.xml;
const parser = new Parser();
parser.parseString(userXml, (err: Error | null, result: any) => {
  if (err) {
    handleError(err);
  } else {
    processResult(result);
  }
});
```

`xml2js` does not resolve external entities and is safe even in TypeScript
projects.

## fast-xml-parser with TypeScript

### Safe

```typescript
import { XMLParser } from 'fast-xml-parser';

const userXml: string = request.body.xml;
const parser = new XMLParser({
  ignoreAttributes: false,
  parseTagValue: true
});
const result: any = parser.parse(userXml);
```

`fast-xml-parser` does not support entity expansion and is safe for
TypeScript projects.

## xmldom with TypeScript

### Safe

```typescript
import { DOMParser } from 'xmldom';

const userXml: string = request.body.xml;
const parser = new DOMParser();
const doc: Document = parser.parseFromString(userXml, 'text/xml');
```

The `xmldom` package does not resolve external entities by default and is
safe for TypeScript.

## Custom entity-resolving parsers

### Vulnerable

```typescript
interface EntityResolver {
  resolve(entity: string): string;
}

function parseXmlWithEntities(userXml: string, resolver: EntityResolver):
    any {
  const entityRegex = /<!ENTITY\s+(\w+)\s+SYSTEM\s+"([^"]+)"/g;
  userXml = userXml.replace(entityRegex, (match: string, name: string,
      url: string) => {
    const content: string = resolver.resolve(url);
    return `<!ENTITY ${name} "${content}">`;
  });
  return libxmljs.parseXml(userXml, { noent: true });
}
```

### Safe

```typescript
function parseXml(userXml: string): any {
  return libxmljs.parseXml(userXml, { noent: false });
}
```

Do not implement custom entity resolution. Use safe parsers that reject or
ignore entity declarations by default.

## Type safety considerations

TypeScript's type system does not prevent XXE vulnerabilities. A function
signature accepting `userXml: string` does not guarantee it is safe to parse;
the safety depends on the parser configuration and the library used. Always:

- Use parsers that disable entities by default (xml2js, fast-xml-parser,
  xmldom).
- If using libxmljs, explicitly verify the `{ noent: false }` option is set
  in the library call itself, not in a separate configuration object that
  might be overlooked.
- Validate XML schema before parsing if the XML structure is known.
