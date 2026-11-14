# PHP XPath injection patterns

Vulnerable-vs-safe snippets for the PHP XPath libraries the
`injection.xpath` scanner recognizes.

## DOMXPath

### Vulnerable

```php
$dom = new DOMDocument();
$dom->load("data.xml");
$xpath = new DOMXPath($dom);

$userId = $_GET["id"];
$result = $xpath->query("//user[@id='$userId']");
$result = $xpath->query("//user[@id='" . $userId . "']");
```

### Safe

```php
$dom = new DOMDocument();
$dom->load("data.xml");
$xpath = new DOMXPath($dom);

$userId = $_GET["id"];
$allowedIds = ["123", "456", "789"];

if (!in_array($userId, $allowedIds)) {
    throw new InvalidArgumentException("Invalid user ID");
}

$result = $xpath->query("//user[@id='$userId']");
```

PHP's `DOMXPath` does not support parameterized XPath queries. Validate the
input against an explicit allowlist before interpolating.

Alternatively, escape XPath special characters:

```php
function escapeXPathString($s) {
    return str_replace(
        ["'", '"', "&", "<", ">"],
        ["&apos;", "&quot;", "&amp;", "&lt;", "&gt;"],
        $s
    );
}

$result = $xpath->query(
    "//user[@id='" . escapeXPathString($userId) . "']"
);
```

## SimpleXML

### Vulnerable

```php
$xml = simplexml_load_file("data.xml");

$userInput = $_GET["name"];
$result = $xml->xpath("//user[@name='$userInput']");
$result = $xml->xpath("//item[@id='" . $userInput . "']");
```

### Safe

```php
$xml = simplexml_load_file("data.xml");

$userInput = $_GET["name"];
$allowedNames = ["admin", "user", "guest"];

if (!in_array($userInput, $allowedNames)) {
    throw new InvalidArgumentException("Invalid name");
}

$result = $xml->xpath("//user[@name='$userInput']");
```

`SimpleXML`'s `xpath()` method does not support parameterization. Validate
the input against an allowlist or escape special characters before
interpolating.

## Comparison

| Library | Parameterized | Recommendation |
|---|---|---|
| `DOMXPath` | No | Validate against allowlist or escape. |
| `SimpleXML` | No | Validate against allowlist or escape. |
