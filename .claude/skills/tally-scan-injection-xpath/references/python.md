# Python XPath injection patterns

Vulnerable-vs-safe snippets for the Python XPath libraries the
`injection.xpath` scanner recognizes. When multiple safe forms exist, the
canonical one is shown first.

## lxml

### Vulnerable

```python
from lxml import etree
user_id = request.args.get("id")
tree = etree.parse("data.xml")
result = tree.xpath(f"//user[@id='{user_id}']")
result = tree.xpath("//user[@id='" + user_id + "']")
result = tree.xpath("//user[@id='%s']" % user_id)
```

### Safe

```python
from lxml import etree
user_id = request.args.get("id")
tree = etree.parse("data.xml")
result = tree.xpath("//user[@id=$id]", id=user_id)
```

`lxml` supports XPath variables via keyword arguments. The `$variable` form
is parameterized and safe. Pass the variable name and value as a keyword
argument to `xpath()`.

## xml.etree.ElementTree

### Vulnerable

```python
import xml.etree.ElementTree as ET
user_id = request.args.get("id")
root = ET.parse("data.xml").getroot()
result = root.findall(f".//user[@id='{user_id}']")
result = root.find(f".//item[@name='{user_name}']")
result = root.iterfind("//user[@id='" + str(user_id) + "']")
```

### Safe

```python
import xml.etree.ElementTree as ET
user_id = request.args.get("id")
root = ET.parse("data.xml").getroot()

ALLOWED_IDS = {"123", "456", "789"}
if user_id not in ALLOWED_IDS:
    raise ValueError(f"Invalid user ID: {user_id}")

result = root.findall(f".//user[@id='{user_id}']")
```

`xml.etree.ElementTree` does not support parameterized XPath. Instead,
validate the input against an explicit allowlist of acceptable values
before interpolating. The allowlist check is the safety measure.

Alternatively, escape XPath special characters:

```python
def escape_xpath_string(s):
    return s.replace("'", "&apos;").replace('"', "&quot;")

result = root.findall(f".//user[@id='{escape_xpath_string(user_id)}']")
```

## Comparison

| Library | Parameterized | Recommendation |
|---|---|---|
| `lxml` | Yes | Use XPath variables (`xpath($var=value)`). |
| `xml.etree.ElementTree` | No | Validate against allowlist or escape. |
