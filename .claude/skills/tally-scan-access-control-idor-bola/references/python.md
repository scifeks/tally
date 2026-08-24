# Python IDOR/BOLA patterns

Vulnerable-vs-safe snippets for the Python frameworks and ORMs the
`access_control.idor_bola` scanner recognizes. When multiple safe forms
exist, the canonical one is shown first.

## Django ORM

### Vulnerable

```python
def user_profile(request):
    user_id = request.GET['id']
    user = User.objects.get(pk=user_id)
    return render(request, 'profile.html', {'user': user})
```

```python
def get_order(request):
    order_id = request.POST['order_id']
    order = Order.objects.get(id=order_id)
    return JsonResponse({'total': order.total})
```

### Safe

```python
def user_profile(request):
    user_id = request.GET['id']
    user = User.objects.get(pk=user_id, id=request.user.id)
    return render(request, 'profile.html', {'user': user})
```

```python
def get_order(request):
    order_id = request.POST['order_id']
    order = Order.objects.get(id=order_id, user=request.user)
    return JsonResponse({'total': order.total})
```

The safe pattern filters the queryset to the authenticated user before
fetching. This ensures only the owner of the resource can access it.

## Django REST Framework ViewSet

### Vulnerable

```python
class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def retrieve(self, request, pk=None):
        order = Order.objects.get(pk=pk)
        serializer = OrderSerializer(order)
        return Response(serializer.data)
```

### Safe

```python
class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user)
```

The safe pattern overrides `get_queryset()` to scope all queries to the
authenticated user. The default `retrieve()` method then uses this
filtered queryset.

## FastAPI

### Vulnerable

```python
@app.get("/api/documents/{doc_id}")
def get_document(doc_id: int, current_user: User = Depends(get_current_user)):
    doc = db.query(Document).get(doc_id)
    return {"title": doc.title, "content": doc.content}
```

### Safe

```python
@app.get("/api/documents/{doc_id}")
def get_document(doc_id: int, current_user: User = Depends(get_current_user)):
    doc = db.query(Document).filter(
        Document.id == doc_id,
        Document.owner_id == current_user.id
    ).first()
    if not doc:
        raise HTTPException(status_code=404)
    return {"title": doc.title, "content": doc.content}
```

Or use a dependency to encapsulate the ownership check:

```python
def get_user_document(
    doc_id: int,
    current_user: User = Depends(get_current_user)
) -> Document:
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc or doc.owner_id != current_user.id:
        raise HTTPException(status_code=404)
    return doc

@app.get("/api/documents/{doc_id}")
def get_document(doc: Document = Depends(get_user_document)):
    return {"title": doc.title, "content": doc.content}
```

The safe pattern filters the query to include both the resource ID and
the ownership constraint, or raises a 404 if the resource does not exist
or is not owned by the current user.

## SQLAlchemy ORM

### Vulnerable

```python
def get_bank_account(request):
    account_id = request.GET['account_id']
    session = get_db_session()
    account = session.query(BankAccount).filter(
        BankAccount.id == account_id
    ).first()
    return account
```

### Safe

```python
def get_bank_account(request):
    account_id = request.GET['account_id']
    user_id = request.user.id
    session = get_db_session()
    account = session.query(BankAccount).filter(
        BankAccount.id == account_id,
        BankAccount.owner_id == user_id
    ).first()
    if not account:
        raise PermissionError("Account not found or not owned by user")
    return account
```

The safe pattern adds an ownership filter to the WHERE clause. Both
conditions must be true for the query to return a result.

## Django's get_object_or_404

### Vulnerable

```python
from django.shortcuts import get_object_or_404

def edit_post(request, post_id):
    post = get_object_or_404(Post, pk=post_id)
    if request.method == 'POST':
        post.title = request.POST['title']
        post.save()
    return render(request, 'edit_post.html', {'post': post})
```

### Safe

```python
from django.shortcuts import get_object_or_404

def edit_post(request, post_id):
    post = get_object_or_404(Post, pk=post_id, author=request.user)
    if request.method == 'POST':
        post.title = request.POST['title']
        post.save()
    return render(request, 'edit_post.html', {'post': post})
```

The shortcut `get_object_or_404` accepts additional filter kwargs. Always
include the ownership check in the kwargs.

## Multi-tenant filtering

For applications with multiple tenants, filter by both the resource ID
and the tenant or owner:

### Vulnerable

```python
def get_tenant_data(request):
    tenant_id = request.GET['tenant_id']
    data = TenantData.objects.get(id=tenant_id)
    return data
```

### Safe

```python
def get_tenant_data(request):
    tenant_id = request.GET['tenant_id']
    user = request.user
    data = TenantData.objects.get(
        id=tenant_id,
        tenant__members=user
    )
    return data
```

or via JWT claims:

```python
def get_tenant_data(request):
    tenant_id = request.GET['tenant_id']
    user_tenant_id = request.user.tenant_id
    if int(tenant_id) != user_tenant_id:
        raise PermissionError("Access denied")
    data = TenantData.objects.get(id=tenant_id)
    return data
```

The safe pattern verifies the tenant either by querying through the
relationship or by comparing the user's tenant ID to the request parameter.
