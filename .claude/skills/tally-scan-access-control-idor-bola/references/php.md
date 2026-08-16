# PHP IDOR/BOLA patterns

Vulnerable-vs-safe snippets for the PHP frameworks and patterns the
`access_control.idor_bola` scanner recognizes. When multiple safe forms
exist, the canonical one is shown first.

## Laravel Eloquent (model find)

### Vulnerable

```php
public function getOrder($id)
{
    $order = Order::find($id);
    return response()->json($order);
}
```

```php
public function deleteComment($id)
{
    $comment = Comment::find($id);
    $comment->delete();
    return response()->json(['status' => 'deleted']);
}
```

### Safe

```php
public function getOrder($id)
{
    $order = Order::where('id', $id)
        ->where('user_id', Auth::id())
        ->first();
    if (!$order) {
        abort(404);
    }
    return response()->json($order);
}
```

```php
public function deleteComment($id)
{
    $comment = Comment::find($id);
    $this->authorize('delete', $comment);
    $comment->delete();
    return response()->json(['status' => 'deleted']);
}
```

The safe patterns either filter the query to the authenticated user or use
Laravel's policy-based authorization via the `authorize()` method.

## Laravel Query Builder

### Vulnerable

```php
public function getUserData($userId)
{
    $user = DB::table('users')
        ->where('id', $userId)
        ->first();
    return response()->json($user);
}
```

### Safe

```php
public function getUserData($userId)
{
    $user = DB::table('users')
        ->where('id', $userId)
        ->where('id', Auth::id())
        ->first();
    if (!$user) {
        abort(404);
    }
    return response()->json($user);
}
```

The safe pattern adds an ownership filter to the WHERE clause.

## Laravel Route Model Binding with Scoped Bindings

### Vulnerable

```php
Route::get('/documents/{document}', function (Document $document) {
    return response()->json($document);
});
```

Without scoped bindings, this route allows any authenticated user to fetch
any document by ID.

### Safe

```php
Route::get('/documents/{document}', function (Document $document) {
    return response()->json($document);
})->middleware(SubstituteBindings::class);

class Document extends Model
{
    public function getRouteKeyName()
    {
        return 'id';
    }

    public function scopeForUser($query, $userId)
    {
        return $query->where('user_id', $userId);
    }
}
```

Or use a policy:

```php
Route::get('/documents/{document}', [DocumentController::class, 'show']);

class DocumentController
{
    public function show(Document $document)
    {
        $this->authorize('view', $document);
        return response()->json($document);
    }
}
```

The safe pattern either scopes the binding or uses a policy to verify the
authenticated user has permission to view the document.

## Laravel Resource Routes with Authorization

### Vulnerable

```php
class PostController extends Controller
{
    public function show($id)
    {
        $post = Post::find($id);
        return view('post.show', ['post' => $post]);
    }
}
```

### Safe

```php
class PostController extends Controller
{
    public function show($id)
    {
        $post = Post::findOrFail($id);
        $this->authorize('view', $post);
        return view('post.show', ['post' => $post]);
    }
}
```

The safe pattern uses `findOrFail()` to return a 404 if the post does not
exist, then calls `authorize()` to verify the authenticated user has
permission to view it.

## Raw PHP with $_GET / $_POST

### Vulnerable

```php
$userId = $_GET['user_id'];
$user = $pdo->query("SELECT * FROM users WHERE id = $userId")->fetch();
echo json_encode($user);
```

### Safe

```php
$userId = $_GET['user_id'];
$currentUserId = $_SESSION['user_id'];
if ((int)$userId !== (int)$currentUserId && !isAdmin()) {
    http_response_code(403);
    exit;
}
$stmt = $pdo->prepare("SELECT * FROM users WHERE id = ?");
$stmt->execute([$userId]);
$user = $stmt->fetch();
echo json_encode($user);
```

The safe pattern checks ownership or admin status before querying, and
uses prepared statements to prevent SQL injection.

## WordPress

### Vulnerable

```php
$post_id = $_GET['post_id'];
$post = get_post($post_id);
return wp_json_encode($post);
```

### Safe

```php
$post_id = $_GET['post_id'];
$current_user = wp_get_current_user();
$post = get_post($post_id);

if (!$post) {
    wp_send_json_error('Not found', 404);
    return;
}
if ($post->post_author != $current_user->ID && !current_user_can(
    'manage_posts'
)) {
    wp_send_json_error('Unauthorized', 403);
}
return wp_json_encode($post);
```

The safe pattern verifies the current user is the post author or has the
capability to manage posts.

## Multi-tenant Laravel

### Vulnerable

```php
public function getTenantData($id)
{
    $data = TenantData::find($id);
    return response()->json($data);
}
```

### Safe

```php
public function getTenantData($id)
{
    $data = TenantData::where('id', $id)
        ->where('tenant_id', Auth::user()->tenant_id)
        ->first();
    if (!$data) {
        abort(404);
    }
    return response()->json($data);
}
```

The safe pattern filters by both the resource ID and the authenticated
user's tenant ID.
