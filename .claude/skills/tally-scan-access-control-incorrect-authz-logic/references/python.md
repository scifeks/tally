# Python authorization logic patterns

Vulnerable-vs-safe snippets for the Python frameworks and libraries the
`access_control.incorrect_authz_logic` scanner recognizes. When multiple
safe forms exist, the canonical one is shown first.

## Django permissions

### Vulnerable

```python
# OR logic in role check
if request.user.groups.filter(name='admin').exists() or \
   request.user.groups.filter(name='user').exists():
    return delete_item(item)

# Always-true check
if request.user.is_authenticated or True:
    perform_admin_action()

# Wrong permission name
@permission_required('view_item')
def delete_item(request, item_id):
    Item.objects.get(id=item_id).delete()
```

### Safe

```python
# Use AND when multiple conditions must both hold
if request.user.groups.filter(name='admin').exists() and \
   request.user.is_active:
    return delete_item(item)

# Use a set of allowed groups
ADMIN_GROUPS = {'admin', 'superuser'}
if request.user.groups.filter(
    name__in=ADMIN_GROUPS
).exists():
    perform_admin_action()

# Use correct permission name
@permission_required('delete_item')
def delete_item(request, item_id):
    Item.objects.get(id=item_id).delete()
```

Django's permission system names permissions as `app_label.action_model`,
e.g. `articles.delete_article`. Use `@permission_required` with the exact
action, not a related one.

## Flask with custom authorization

### Vulnerable

```python
# Negated check that over-permits
def admin_only():
    if current_user.role != 'guest':
        perform_admin_action()

# Wrong field in ownership check
def edit_post(post_id):
    post = Post.query.get(post_id)
    if post.id == current_user.id:
        post.update()

# Overly broad role check
if current_user.role in ['admin', 'editor', 'moderator', 'user']:
    delete_comment(comment_id)
```

### Safe

```python
# Positive assertion
def admin_only():
    if current_user.role == 'admin':
        perform_admin_action()

# Compare the correct field
def edit_post(post_id):
    post = Post.query.get(post_id)
    if post.owner_id == current_user.id:
        post.update()

# List only necessary roles
DELETION_ROLES = {'admin', 'moderator'}
if current_user.role in DELETION_ROLES:
    delete_comment(comment_id)
```

## DRF permission classes

### Vulnerable

```python
# Check wrong permission
class DeletePostPermission(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return request.user.has_perm('posts.view_post')

# Overly broad check
class AdminOrReadOnlyPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.role in ['admin', 'staff', 'editor']
```

### Safe

```python
# Check the permission that matches the operation
class DeletePostPermission(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return request.user.has_perm('posts.delete_post')

# Scope to necessary roles only
class AdminOnlyPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.role == 'admin'
```

Use a separate permission class for each operation. Do not reuse view
permissions for object deletion.

## Manual role-based access control

### Vulnerable

```python
# String case mismatch
def promote_to_admin(user_id):
    user = User.query.get(user_id)
    if user.role.lower() == 'admin':
        raise PermissionError()

# OR instead of AND
if user.has_perm('create') or user.has_perm('edit'):
    handle_privileged_action()

# Short-circuit logic
def is_authorized():
    return user.has_perm('action') or True
```

### Safe

```python
# Case-preserving comparison
ADMIN_ROLE = 'Admin'  # Stored with capital A
if user.role != ADMIN_ROLE:
    raise PermissionError()

# Use AND when both conditions must hold
if user.has_perm('create') and user.has_perm('edit'):
    handle_privileged_action()

# Explicit check, no short-circuit
def is_authorized():
    return user.has_perm('action')
```

Use enum or module-level constants for role names to avoid typos and
case-sensitivity bugs.
