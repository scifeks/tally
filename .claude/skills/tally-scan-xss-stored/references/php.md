# PHP stored XSS patterns

Vulnerable-vs-safe snippets for PHP frameworks where
persistence-sourced data reaches HTML output. When multiple safe
forms exist, the canonical one is shown first.

## Raw echo

### Vulnerable

```php
$row = $pdo->query("SELECT * FROM comments WHERE id = ?")->fetch();
echo "<p>" . $row['body'] . "</p>";
echo "<span>{$row['author']}</span>";
```

### Safe

```php
echo "<p>" . htmlspecialchars($row['body'], ENT_QUOTES, 'UTF-8')
    . "</p>";
echo "<span>"
    . htmlspecialchars($row['author'], ENT_QUOTES, 'UTF-8')
    . "</span>";
```

Always pass `ENT_QUOTES` and `'UTF-8'` to `htmlspecialchars()`.
Without `ENT_QUOTES`, single-quoted attribute contexts remain
vulnerable.

## Laravel Blade

### Vulnerable

```php
{{-- Blade template --}}
<div class="content">{!! $post->body !!}</div>
<p>{!! $comment->text !!}</p>
```

### Safe

```php
<div class="content">{{ $post->body }}</div>
<p>{{ $comment->text }}</p>
```

Blade's `{{ }}` syntax runs `htmlspecialchars()` automatically.
The `{!! !!}` syntax outputs raw HTML. Use `{{ }}` for all
user-sourced data. If the field must render HTML, sanitize at
write time with a library like `mews/purifier`.

## Twig (Symfony)

### Vulnerable

```twig
<div class="article-body">{{ article.content|raw }}</div>
<p>{{ feedback.message|raw }}</p>
```

### Safe

```twig
<div class="article-body">{{ article.content }}</div>
<p>{{ feedback.message }}</p>
```

Twig auto-escapes by default. The `|raw` filter disables escaping.
Remove `|raw` for user-sourced data. Use `|e('html')` to make
escaping explicit when needed.

## WordPress

### Vulnerable

```php
$custom = get_post_meta($post_id, 'user_bio', true);
echo '<div class="bio">' . $custom . '</div>';
echo the_content();  // unfiltered if no sanitization on save
```

### Safe

```php
$custom = get_post_meta($post_id, 'user_bio', true);
echo '<div class="bio">'
    . esc_html($custom)
    . '</div>';
echo wp_kses_post(get_the_content());
```

WordPress provides context-specific escaping functions:
`esc_html()` for element content, `esc_attr()` for attribute
values, `esc_url()` for URLs. `wp_kses_post()` allows a safe
subset of HTML tags.
