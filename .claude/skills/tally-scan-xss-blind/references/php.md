# PHP blind XSS patterns

Vulnerable-vs-safe snippets for PHP frameworks where
user-submitted data is stored and later rendered in admin or
internal contexts without escaping.

## Admin panel echoing user submissions

### Vulnerable

```php
// Admin controller
public function showSubmission($id)
{
    $submission = ContactForm::find($id);
    return view('admin.submission', compact('submission'));
}
```

```php
{{-- admin/submission.blade.php --}}
<div class="message">{!! $submission->message !!}</div>
<p>From: {!! $submission->name !!}</p>
```

### Safe

```php
<div class="message">{{ $submission->message }}</div>
<p>From: {{ $submission->name }}</p>
```

Admin templates need the same escaping as public-facing templates.
Replace `{!! !!}` with `{{ }}` for user-submitted data.

## WordPress admin screen

### Vulnerable

```php
// Admin page callback
function render_user_bios_page() {
    $users = get_users();
    foreach ($users as $user) {
        echo '<tr><td>'
            . get_user_meta($user->ID, 'bio', true)
            . '</td></tr>';
    }
}
```

### Safe

```php
function render_user_bios_page() {
    $users = get_users();
    foreach ($users as $user) {
        echo '<tr><td>'
            . esc_html(get_user_meta($user->ID, 'bio', true))
            . '</td></tr>';
    }
}
```

User meta fields accept arbitrary input from profile forms.
Admin screens rendering these values need `esc_html()`.

## Twig admin template

### Vulnerable

```twig
{# admin/feedback.html.twig #}
{% for item in feedback %}
<div class="feedback-body">{{ item.message|raw }}</div>
{% endfor %}
```

### Safe

```twig
{% for item in feedback %}
<div class="feedback-body">{{ item.message }}</div>
{% endfor %}
```

Remove `|raw` in admin templates. Twig auto-escapes by default.

## Laravel email template

### Vulnerable

```php
// Mailable
public function build()
{
    return $this->view('emails.ticket-notification')
        ->with(['ticket' => $this->ticket]);
}
```

```php
{{-- emails/ticket-notification.blade.php --}}
<p>New ticket from {{ $ticket->name }}:</p>
<div>{!! $ticket->body !!}</div>
```

### Safe

```php
<p>New ticket from {{ $ticket->name }}:</p>
<div>{{ $ticket->body }}</div>
```

Email templates should use `{{ }}` for user-submitted data.
HTML email clients may execute scripts in some configurations.
