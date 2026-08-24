# JavaScript XPath injection patterns

Vulnerable-vs-safe snippets for the JavaScript XPath libraries the
`injection.xpath` scanner recognizes.

## xpath npm package

### Vulnerable

```javascript
const xpath = require("xpath");
const dom = require("xmldom").DOMParser;

const userInput = req.query.name;
const doc = new dom().parseFromString(xmlData);
const result = xpath.select("//user[@name='" + userInput + "']", doc);
const result2 = xpath.select(`//user[@name='${userInput}']`, doc);
```

### Safe

```javascript
const xpath = require("xpath");
const dom = require("xmldom").DOMParser;

const userInput = req.query.name;
const allowedNames = ["admin", "user", "guest"];

if (!allowedNames.includes(userInput)) {
    throw new Error("Invalid name");
}

const doc = new dom().parseFromString(xmlData);
const result = xpath.select(`//user[@name='${userInput}']`, doc);
```

The `xpath` npm package does not support parameterized queries. Validate
the input against an allowlist or escape XPath special characters before
interpolating.

Escape function:

```javascript
function escapeXPathString(s) {
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

## xmldom

### Vulnerable

```javascript
const { DOMParser } = require("xmldom");
const userInput = req.query.id;

const doc = new DOMParser().parseFromString(xmlData);
const result = doc.evaluate(
    `//user[@id='${userInput}']`,
    doc,
    null,
    0,
    null
);
```

### Safe

```javascript
const { DOMParser } = require("xmldom");
const userInput = req.query.id;
const allowedIds = ["123", "456", "789"];

if (!allowedIds.includes(userInput)) {
    throw new Error("Invalid ID");
}

const doc = new DOMParser().parseFromString(xmlData);
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
