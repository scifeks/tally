# PHP XXE injection patterns

Vulnerable-vs-safe snippets for the PHP XML libraries the `xxe` scanner
recognizes.

## SimpleXML

### Vulnerable (PHP < 8.0)

```php
$userXml = $_POST['xml'];
$dom = simplexml_load_string($userXml);

$userFile = $_FILES['xml_file']['tmp_name'];
$dom = simplexml_load_file($userFile);
```

### Safe (PHP < 8.0)

```php
libxml_disable_entity_loader(true);
$userXml = $_POST['xml'];
$dom = simplexml_load_string($userXml);
libxml_disable_entity_loader(false);

$userXml = $_POST['xml'];
$dom = simplexml_load_string(
    $userXml,
    'SimpleXMLElement',
    LIBXML_NONET
);
```

On PHP < 8.0, entities are enabled by default. Disable entity loading with
`libxml_disable_entity_loader(true)` before parsing, or pass `LIBXML_NONET`
to restrict network access.

### Safe (PHP 8.0+)

```php
$userXml = $_POST['xml'];
$dom = simplexml_load_string($userXml);
```

PHP 8.0+ disables external entity resolution by default. The above calls are
safe unless `LIBXML_NOENT` is explicitly passed.

## DOMDocument

### Vulnerable

```php
$userXml = $_POST['xml'];
$dom = new DOMDocument();
$dom->loadXML($userXml);

$userFile = $_FILES['xml_file']['tmp_name'];
$dom = new DOMDocument();
$dom->load($userFile);
```

### Safe

```php
$userXml = $_POST['xml'];
$dom = new DOMDocument();
$dom->load('php://memory', LIBXML_NOENT);

$userXml = $_POST['xml'];
$dom = new DOMDocument();
libxml_disable_entity_loader(true);
$dom->loadXML($userXml);
libxml_disable_entity_loader(false);
```

Disable entity loading before calling `loadXML()` or `load()`. Alternatively,
pass `LIBXML_NOENT` flag to prevent entity expansion (though this flag name
is misleading; it must be omitted to disable entities).

## XMLReader

### Vulnerable

```php
$userXml = $_POST['xml'];
$reader = new XMLReader();
$reader->XML($userXml);
```

### Safe

```php
$userXml = $_POST['xml'];
$reader = new XMLReader();
libxml_disable_entity_loader(true);
$reader->XML($userXml);
libxml_disable_entity_loader(false);
```

Disable entity loading before opening or parsing XML with XMLReader.

## libxml settings per function

On PHP < 8.0, the safest approach is to disable entity loading globally
before parsing:

### Safe global setting

```php
libxml_disable_entity_loader(true);

$userXml = $_POST['xml'];
$dom = new DOMDocument();
$dom->loadXML($userXml);

$userXml2 = $_POST['other_xml'];
$dom2 = new DOMDocument();
$dom2->loadXML($userXml2);

libxml_disable_entity_loader(false);
```

The `libxml_disable_entity_loader()` function affects all XML parsers in the
process until reset. Call it before parsing untrusted XML, then restore it
afterward to avoid affecting other code.

## Doctrine DBAL

### Vulnerable

```php
$xml = $_POST['xml'];
$result = $conn->executeQuery("SELECT ...", []);
```

This is not a direct XML parsing sink; Doctrine handles SQL. However, if
Doctrine is used to read XML from a database and then parse it, ensure the
parsing step uses the safe patterns above.

### Safe

Use the safe patterns from DOMDocument or SimpleXML when parsing the result.
