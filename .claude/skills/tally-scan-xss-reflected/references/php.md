# PHP reflected XSS patterns

Vulnerable-vs-safe snippets for PHP frameworks where same-request
data reaches HTML output. When multiple safe forms exist, the
canonical one is shown first.

## Raw echo of superglobals

### Vulnerable

```php
echo "<p>Search results for: " . $_GET['search'] . "</p>";
echo "<input value='" . $_POST['username'] . "'>";
echo "Referrer: " . $_SERVER['HTTP_REFERER'];
```

### Safe

```php
echo "<p>Search results for: "
    . htmlspecialchars($_GET['search'], ENT_QUOTES, 'UTF-8')
    . "</p>";
echo "<input value='"
    . htmlspecialchars($_POST['username'], ENT_QUOTES, 'UTF-8')
    . "'>";
```

Always pass `ENT_QUOTES` and `'UTF-8'` to `htmlspecialchars()`.
Apply encoding at every output point.

## Laravel Blade

### Vulnerable

```php
<p>Results for: {!! request()->input('q') !!}</p>
<input value="{!! old('name') !!}">
```

### Safe

```php
<p>Results for: {{ request()->input('q') }}</p>
<input value="{{ old('name') }}">
```

Blade `{{ }}` runs `htmlspecialchars()` automatically.
`{!! !!}` outputs raw HTML. Use `{{ }}` for request data.

## Twig (Symfony)

### Vulnerable

```twig
<p>{{ app.request.get('q')|raw }}</p>
```

### Safe

```twig
<p>{{ app.request.get('q') }}</p>
```

Twig auto-escapes by default. The `|raw` filter disables
escaping. Remove `|raw` for request-sourced data.

## WordPress

### Vulnerable

```php
echo '<p>Not found: ' . $_GET['page'] . '</p>';
echo '<p>' . $_SERVER['REQUEST_URI'] . '</p>';
```

### Safe

```php
echo '<p>Not found: ' . esc_html($_GET['page']) . '</p>';
echo '<p>' . esc_url($_SERVER['REQUEST_URI']) . '</p>';
```

Use `esc_html()` for element content, `esc_attr()` for attribute
values, `esc_url()` for URL contexts.

## Error page reflection

### Vulnerable

```php
http_response_code(404);
echo "<h1>Page not found: " . $_SERVER['REQUEST_URI'] . "</h1>";
```

### Safe

```php
http_response_code(404);
echo "<h1>Page not found: "
    . htmlspecialchars(
        $_SERVER['REQUEST_URI'], ENT_QUOTES, 'UTF-8'
    )
    . "</h1>";
```

Custom error pages often reflect the requested URL. The URI can
contain attacker-controlled path segments or query parameters.
