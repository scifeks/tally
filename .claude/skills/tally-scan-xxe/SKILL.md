---
name: tally-scan-xxe
description: >
  Scan the target repo for XML External Entity (XXE) injection defects.
  Detects XML parsers processing user-supplied XML with external entity
  resolution enabled. Emits findings shaped for Tally MCP submission
  (rule_id `xxe`, CWE-611, severity high). Invoke when the user says
  "XXE", "XML external entity", "check for XXE injection", or when
  dispatched by `tally-scan-external`.
---

# Tally scanner: XML External Entity (XXE) injection

Detects sinks where user-controlled XML data reaches an XML parser without
disabling external entity resolution. Runs per-file in the target repo
(as dispatched by the `tally-scan-external` orchestrator, or standalone
when the user invokes this skill directly). Emits a JSON list of findings;
the orchestrator or the user submits them to Tally through the `submit_finding`
MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `xxe` |
| Primary CWE | `CWE-611` |
| Secondary CWE | `CWE-776` |
| OWASP 2025 category | `Injection` |
| Default severity | `high` |
| Parent label (dedup) | `XXE` |

Source: `docs/roadmap/TAL-148/taxonomy.md` T3 row for XXE.

## Detection matrix

### Python

- **lxml string parse**: `lxml.etree.fromstring(user_xml)` or
  `lxml.etree.fromstring(user_xml, parser)` where the parser does not
  disable entity resolution.
- **lxml file parse**: `lxml.etree.parse(user_file)` without setting
  `resolve_entities=False` on the parser.
- **SAX parser**: `xml.sax.parseString(user_xml)` or
  `xml.sax.parse(user_file)` with entity expansion enabled.
- **DOM parser**: `xml.dom.minidom.parseString(user_xml)` or
  `xml.dom.minidom.parse(user_file)` without disabling DTD processing.
- **Weak defusedxml usage**: using `defusedxml` library correctly is safe
  by design; unsafe calls to the above libraries (outside defusedxml) are
  vulnerable.

Defer to `references/python.md` for vulnerable-vs-safe snippets.

### PHP

- **SimpleXML**: `simplexml_load_string($userXml)` or
  `simplexml_load_file($userFile)` on PHP < 8.0 (entities enabled by default).
  On PHP 8.0+, same calls are safe unless `LIBXML_NOENT` flag is passed.
- **DOMDocument**: `$dom->loadXML($userXml)` or `$dom->load($userFile)` with
  entity loading enabled or without disabling entity expansion.
- **XMLReader**: `$reader->xml($userXml)` or `$reader->open($userFile)` with
  entity expansion enabled.
- **Weak libxml settings**: relying on `libxml_disable_entity_loader(true)`
  without checking if the setting persists across function calls.

Defer to `references/php.md` for vulnerable-vs-safe snippets.

### JavaScript

- **libxmljs with entity resolution**: `libxmljs.parseXml(userXml, {noent:
  true})` explicitly enables entity expansion.
- **Custom XML parser**: custom DOM implementations that traverse entity
  definitions when `noent` or entity-resolution flag is enabled.
- **Parsers safe by default**: `xml2js`, `fast-xml-parser`, and `xmldom` do
  not resolve external entities by default and are safe.

Defer to `references/javascript.md` for vulnerable-vs-safe snippets.

### TypeScript

- **libxmljs bindings**: same as JavaScript XXE risk.
- **Custom entity-resolving parsers**: TypeScript wrappers around libxmljs or
  hand-written entity resolvers.
- **Same JavaScript sinks apply** on the Node runtime.

Defer to `references/typescript.md` for vulnerable-vs-safe snippets.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the parser call.
- `meta.code_snippet`: 2-6 lines of source containing the sink.
- `meta.reasoning`: one sentence explaining why the pattern is an XXE at
  this location.
- When the taint source is in the same file:
  `meta.taint_source` naming the request parameter or upstream variable
  that reaches the sink.

Set `confidence`:

- `confirmed` when a taint source is traced from a request handler to the
  sink in the same file, or through a same-file helper.
- `probable` when the sink pattern matches and the value is clearly a
  variable (not a constant), but the source is inferred.
- `potential` when the sink is suspicious but the value is not obviously
  user-controlled.

## Output payload skeleton

Emit one JSON object per finding with these fixed fields for `xxe`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing the sink, the source, and what an
  attacker can do via XXE>",
  "severity": "high",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-611", "CWE-776"],
  "finding_type": ["vulnerability"],
  "rule_id": "xxe",
  "meta": {
    "title": "<short human title, e.g. 'XXE injection via lxml
    parsing'>",
    "owasp_name": "Injection",
    "remediation": "<per-finding, per D19; see remediation guidance
    below>",
    "code_snippet": "<2-6 lines of source containing the sink>",
    "taint_source": "<request parameter or upstream variable, when
    traceable>",
    "reasoning": "<one sentence explaining the defect at this location>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for the full
field list and validator behavior.

## Remediation guidance for the scanner

Per D19, write `meta.remediation` inline based on the actual library
observed in the code. Examples of good remediation strings:

- **lxml (Python)**: `Disable external entity resolution by constructing
  a parser with `etree.XMLParser(resolve_entities=False)` and passing it
  to `parse()` or `fromstring()`.`
- **xml.sax (Python)**: `Pass a handler that rejects external entities.
  Use the `defusedxml.sax` module, which wraps the standard library and
  disables entity expansion by default.`
- **SimpleXML (PHP < 8.0)**: `On PHP < 8.0, use the `defusedxml` PECL
  extension or call `libxml_disable_entity_loader(true)` before loading;
  on PHP 8.0+, SimpleXML is safe by default.`
- **DOMDocument (PHP)**: `Disable entity loading before calling loadXML or
  load: set the `LIBXML_NOENT` flag to false, and consider calling
  `libxml_disable_entity_loader(true)`.`
- **libxmljs (JavaScript/TypeScript)**: `Remove the `{noent: true}` flag
  from the parseXml call. If entity expansion is not needed, omit the
  option entirely.`
- **Dynamic XML parsing**: `If the XML schema is known and fixed, parse
  only the necessary elements and ignore DTD declarations. If the XML must
  come from user input, validate its structure against an XML schema before
  parsing.`

Keep it two to four sentences. Vague guidance ("disable external entities")
is worse than no guidance.

## Common false positives

- **defusedxml library calls**: `defusedxml.etree.parse()`,
  `defusedxml.sax.parseString()` are safe by design and must not be
  flagged.
- **Static XML parsing**: parsing of XML literals or read-only config files
  with no user reachability is safe regardless of entity settings.
- **xml.etree.ElementTree (Python 3.8+)**: the stdlib ElementTree has entity
  resolution disabled by default in Python 3.8 and later. Do not flag it.
- **safe-by-default parsers**: `xml2js`, `fast-xml-parser`, and `xmldom` in
  JavaScript do not resolve entities and are safe without configuration.
- **PHP 8.0+ SimpleXML**: `simplexml_load_string($xml)` is safe on PHP 8.0+
  unless the `LIBXML_NOENT` flag is explicitly passed.
- **Constants and enums**: parsing of module-level constants or enum values
  representing XML templates with no user reachability is safe. Confirm the
  value is not reassigned from a request.

## References

- `references/python.md`: Python patterns for lxml, xml.sax, xml.dom.minidom,
  defusedxml.
- `references/php.md`: PHP patterns for SimpleXML, DOMDocument, XMLReader,
  libxml settings.
- `references/javascript.md`: Node patterns for libxmljs, xml2js,
  fast-xml-parser, xmldom.
- `references/typescript.md`: TypeScript patterns for libxmljs bindings and
  custom parsers.
