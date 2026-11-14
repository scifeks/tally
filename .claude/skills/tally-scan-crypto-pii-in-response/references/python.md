# Python PII in response patterns

Vulnerable and safe snippets for Python API response handling the
`crypto.pii_in_response` scanner recognizes.

## Django REST Framework serializer

### Vulnerable

```python
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = '__all__'
```

### Safe

```python
class UserResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email']
```

`fields = '__all__'` exposes every model column, including `password`,
`ssn`, `date_of_birth`, and other sensitive fields added to the model
later.

## FastAPI Pydantic response model

### Vulnerable

```python
class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    ssn: str
    date_of_birth: date
    password_hash: str

@app.get("/users/{id}", response_model=UserResponse)
async def get_user(id: int):
    return await User.get(id)
```

### Safe

```python
class UserResponse(BaseModel):
    id: int
    name: str
    email: str

@app.get("/users/{id}", response_model=UserResponse)
async def get_user(id: int):
    return await User.get(id)
```

Create a separate response model that includes only the fields the client
needs.

## Flask jsonify

### Vulnerable

```python
@app.route('/users/<int:id>')
def get_user(id):
    user = User.query.get_or_404(id)
    return jsonify(user.__dict__)
```

### Safe

```python
@app.route('/users/<int:id>')
def get_user(id):
    user = User.query.get_or_404(id)
    return jsonify({
        'id': user.id,
        'name': user.name,
        'email': user.email,
    })
```

Never serialize `__dict__` or `to_dict()` directly. Select only the
fields the client needs.
