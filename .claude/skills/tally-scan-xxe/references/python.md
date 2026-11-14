# Python XXE injection patterns

Vulnerable-vs-safe snippets for Python XML parsers the `xxe` scanner
recognizes. When multiple safe forms exist, the canonical one is shown
first.

## lxml.etree

### Vulnerable

```python
user_xml = request.get_data()
tree = etree.fromstring(user_xml)

user_file = request.files['xml_file']
tree = etree.parse(user_file)
```

### Safe

```python
parser = etree.XMLParser(resolve_entities=False)
user_xml = request.get_data()
tree = etree.fromstring(user_xml, parser=parser)

parser = etree.XMLParser(resolve_entities=False)
user_file = request.files['xml_file']
tree = etree.parse(user_file, parser=parser)
```

Set `resolve_entities=False` on the parser to prevent external entity
expansion. The parser object can be reused across multiple `parse()` or
`fromstring()` calls.

## xml.sax

### Vulnerable

```python
user_xml = request.get_data()
handler = MyHandler()
parser = xml.sax.make_parser()
parser.setContentHandler(handler)
parser.parseString(user_xml)
```

### Safe

```python
from defusedxml import sax

user_xml = request.get_data()
handler = MyHandler()
sax.parseString(user_xml, ContextHandler=handler)
```

Use `defusedxml.sax` which disables entity expansion by default. The
stdlib `xml.sax` module does not provide a way to disable entities in the
standard API.

## xml.dom.minidom

### Vulnerable

```python
user_xml = request.get_data()
dom = xml.dom.minidom.parseString(user_xml)

user_file = request.files['xml_file']
dom = xml.dom.minidom.parse(user_file)
```

### Safe

```python
from defusedxml import minidom

user_xml = request.get_data()
dom = minidom.parseString(user_xml)

user_file = request.files['xml_file']
dom = minidom.parse(user_file)
```

Use `defusedxml.minidom` which wraps the stdlib module and disables DTD
processing and entity expansion.

## xml.etree.ElementTree (Python 3.8+)

### Vulnerable (Python < 3.8)

```python
user_xml = request.get_data()
root = xml.etree.ElementTree.fromstring(user_xml)
```

### Safe (Python 3.8+)

```python
user_xml = request.get_data()
root = xml.etree.ElementTree.fromstring(user_xml)
```

Python 3.8+ disables external entity resolution by default in ElementTree.
On Python 3.7 or earlier, use `defusedxml.ElementTree` instead.

## defusedxml

### Safe

```python
from defusedxml.ElementTree import parse, fromstring

user_xml = request.get_data()
root = fromstring(user_xml)

user_file = request.files['xml_file']
tree = parse(user_file)
```

The `defusedxml` package wraps all stdlib XML libraries and disables entity
expansion, DTD processing, and billion-laughs attacks by default. It is the
recommended approach for processing untrusted XML in Python.

## Streaming XML parsing

For large or streaming XML, use `iterparse` with entity resolution disabled:

### Vulnerable

```python
user_file = request.files['xml_file']
for event, elem in etree.iterparse(user_file):
    process(elem)
```

### Safe

```python
parser = etree.XMLParser(resolve_entities=False)
user_file = request.files['xml_file']
for event, elem in etree.iterparse(user_file, events=('start',
'end'), parser=parser):
    process(elem)
```

Pass the safe parser configuration to `iterparse`.
