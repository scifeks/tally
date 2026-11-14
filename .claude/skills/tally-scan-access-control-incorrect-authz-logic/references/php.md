# PHP authorization logic patterns

Vulnerable-vs-safe snippets for the PHP frameworks and libraries the
`access_control.incorrect_authz_logic` scanner recognizes. When multiple
safe forms exist, the canonical one is shown first.

## Laravel gates and policies

### Vulnerable

```php
// Wrong gate definition; gate checks wrong condition
Gate::define('delete-post', function ($user, $post) {
    return $user->can('view');  // Should check 'delete'
});

// Wrong action in authorize
public function delete(Post $post)
{
    $this->authorize('update', $post);  // Should be 'delete'
    $post->delete();
}

// Overly broad allowed roles
Gate::define('admin', function ($user) {
    return in_array($user->role, ['admin', 'editor', 'moderator']);
});
```

### Safe

```php
// Gate definition checks the correct permission
Gate::define('delete-post', function ($user, $post) {
    return $user->can('delete') && $post->author_id === $user->id;
});

// Correct action in authorize
public function delete(Post $post)
{
    $this->authorize('delete', $post);
    $post->delete();
}

// Only necessary roles
Gate::define('admin', function ($user) {
    return $user->role === 'admin';
});
```

Always define gates to check the operation being performed. A gate for
deletion must verify the delete action, not a read action.

## Manual role checks

### Vulnerable

```php
// Negated check that over-permits
if ($user->role !== 'guest') {
    perform_privileged_action();
}

// Overly broad array
if (in_array($user->role, ['admin', 'editor', 'staff', 'user'])) {
    delete_resource();
}

// OR logic with multiple conditions
if ($user->role === 'admin' || $user->is_moderator) {
    ban_user();
}
```

### Safe

```php
// Positive assertion
if ($user->role === 'admin') {
    perform_privileged_action();
}

// Only necessary roles
$allowed = ['admin', 'moderator'];
if (in_array($user->role, $allowed)) {
    delete_resource();
}

// AND when multiple conditions must both hold
if ($user->role === 'admin' && $user->is_active) {
    ban_user();
}
```

Prefer positive assertions (`=== 'admin'`) over negated checks. Negation
is error-prone when roles change.

## Spatie Laravel permissions

### Vulnerable

```php
// Wrong permission in check
if ($user->hasPermission('view')) {
    $user->delete();
}

// Overly broad role list
if ($user->hasAnyRole(['admin', 'editor', 'moderator', 'user'])) {
    $resource->publish();
}

// OR condition when AND is needed
if ($user->hasPermission('create') || $user->hasPermission('edit')) {
    perform_admin_action();
}
```

### Safe

```php
// Check permission that matches the operation
if ($user->hasPermission('delete_user')) {
    $user->delete();
}

// Only necessary roles
$admin_roles = ['admin', 'super-admin'];
if ($user->hasAnyRole($admin_roles)) {
    $resource->publish();
}

// AND when both permissions required
if ($user->hasPermission('create') && $user->hasPermission('review')) {
    perform_admin_action();
}
```

Use the permission that describes the operation. Deleting requires a
'delete_' permission, not a 'view_' permission.

## WordPress user role checks

### Vulnerable

```php
// Negated check
if (! current_user_can('manage_options')) {
    wp_die('Not authorized');
    process_admin_function();
}

// Wrong capability
if (current_user_can('edit_pages')) {
    delete_user($user_id);
}

// Overly permissive
if (current_user_can('subscriber') || current_user_can('contributor')) {
    perform_sensitive_action();
}
```

### Safe

```php
// Positive assertion
if (current_user_can('manage_options')) {
    process_admin_function();
}

// Check the capability for the operation
if (current_user_can('delete_users')) {
    delete_user($user_id);
}

// Check with AND
if (current_user_can('manage_options') && is_plugin_active('my-plugin')) {
    perform_sensitive_action();
}
```

WordPress capabilities map to specific actions. Use `delete_users` for user
deletion, `edit_posts` for editing posts, etc.
