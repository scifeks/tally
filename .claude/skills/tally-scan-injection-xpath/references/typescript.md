# TypeScript XPath injection patterns

Vulnerable-vs-safe snippets for the TypeScript XPath libraries the
`injection.xpath` scanner recognizes. TypeScript patterns mirror JavaScript
but include type annotations.

## xpath with TypeScript

### Vulnerable

```typescript
import * as xpath from "xpath";
import { DOMParser } from "xmldom";

const userInput: string = req.query.name;
const doc: any = new DOMParser().parseFromString(xmlData);
const result = xpath.select(
    `//user[@name='${userInput}']`,
    doc
);
```

### Safe

```typescript
import * as xpath from "xpath";
import { DOMParser } from "xmldom";

const userInput: string = req.query.name;
const allowedNames: Set<string> = new Set(["admin", "user", "guest"]);

if (!allowedNames.has(userInput)) {
    throw new Error("Invalid name");
}

const doc: any = new DOMParser().parseFromString(xmlData);
const result = xpath.select(
    `//user[@name='${userInput}']`,
    doc
);
```

The `xpath` package does not support parameterized queries. Validate the
input against an allowlist or escape XPath special characters.

Escape function:

```typescript
function escapeXPathString(s: string): string {
    return s
        .replace(/'/g, "&apos;")
        .replace(/"/g, "&quot;")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
}

const result = xpath.select(
    `//user[@name='${escapeXPathString(userInput)}']`,
    doc
);
```

## xmldom (typed) via @types/xmldom

### Vulnerable

```typescript
import { DOMParser, Document } from "@xmldom/xmldom";

const userInput: string = req.query.id;
const doc: Document = new DOMParser().parseFromString(xmlData);
const result = doc.evaluate(
    `//user[@id='${userInput}']`,
    doc,
    null,
    0,
    null
);
```

### Safe

```typescript
import { DOMParser, Document } from "@xmldom/xmldom";

const userInput: string = req.query.id;
const allowedIds: string[] = ["123", "456", "789"];

if (!allowedIds.includes(userInput)) {
    throw new Error("Invalid ID");
}

const doc: Document = new DOMParser().parseFromString(xmlData);
const result = doc.evaluate(
    `//user[@id='${userInput}']`,
    doc,
    null,
    0,
    null
);
```

`xmldom`'s `evaluate()` method does not support parameterized XPath.
Validate the input against an allowlist or escape special characters.

## Comparison

| Library | Parameterized XPath | Recommendation |
|---|---|---|
| `xpath` npm | No | Validate against allowlist or escape special characters. |
| `xmldom` | No | Validate against allowlist or escape special characters. |

TypeScript's static type system does not prevent XPath injection. The same
validation and escaping patterns from JavaScript apply; type annotations
provide no protection against interpolation vulnerabilities.
