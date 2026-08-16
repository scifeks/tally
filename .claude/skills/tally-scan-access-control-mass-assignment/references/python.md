# Python mass assignment patterns

Vulnerable-vs-safe snippets for the Python frameworks the
`access_control.mass_assignment` scanner recognizes.

## Django ORM

### Vulnerable

```python
from django import forms
from myapp.models import User

class UserForm(forms.ModelForm):
    class Meta:
        model = User
        fields = '__all__'

def create_user(request):
    form = UserForm(request.POST)
    if form.is_valid():
        form.save()

def update_user(request):
    user = User.objects.get(id=request.POST['id'])
    user = User.objects.filter(id=request.POST['id']).update(
        **request.POST.dict()
    )
```

An attacker can set `is_staff`, `is_superuser`, or any other field.

### Safe

```python
class UserForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name']

def create_user(request):
    form = UserForm(request.POST)
    if form.is_valid():
        form.save()

def update_user(request):
    user = User.objects.get(id=request.POST['id'])
    user.username = request.POST.get('username', user.username)
    user.email = request.POST.get('email', user.email)
    user.save()
```

Explicit `fields` list whitelists which model fields the form accepts.

## Django REST Framework Serializer

### Vulnerable

```python
from rest_framework import serializers
from myapp.models import User

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = '__all__'

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
```

An attacker can modify any field in the User model.

### Safe

```python
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']
        read_only_fields = ['id']

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
```

Explicit `fields` tuple restricts which model fields are exposed to
the serializer. Read-only fields cannot be modified via the API.

## FastAPI with Pydantic

### Vulnerable

```python
from fastapi import FastAPI, Request
from sqlalchemy.orm import Session
from myapp.models import User

app = FastAPI()

@app.post("/users")
async def create_user(request: Request, db: Session):
    data = await request.json()
    user = User(**data)
    db.add(user)
    db.commit()
    return user

@app.put("/users/{user_id}")
async def update_user(user_id: int, data: dict, db: Session):
    user = db.query(User).filter(User.id == user_id).first()
    for key, value in data.items():
        setattr(user, key, value)
    db.commit()
    return user
```

An attacker can set any field by including it in the request body.

### Safe

```python
from pydantic import BaseModel

class UserCreate(BaseModel):
    username: str
    email: str
    first_name: str = None
    last_name: str = None

class UserUpdate(BaseModel):
    email: str = None
    first_name: str = None

@app.post("/users")
async def create_user(user_data: UserCreate, db: Session):
    user = User(
        username=user_data.username,
        email=user_data.email,
        first_name=user_data.first_name,
        last_name=user_data.last_name,
    )
    db.add(user)
    db.commit()
    return user

@app.put("/users/{user_id}")
async def update_user(user_id: int, user_data: UserUpdate, db: Session):
    user = db.query(User).filter(User.id == user_id).first()
    if user_data.email:
        user.email = user_data.email
    if user_data.first_name:
        user.first_name = user_data.first_name
    db.commit()
    return user
```

Separate Pydantic models (DTOs) for input define exactly which fields
the endpoint accepts. Only whitelisted fields are assigned to the ORM
model.

## SQLAlchemy with direct dict

### Vulnerable

```python
from sqlalchemy.orm import Session
from myapp.models import User

def update_user(user_id: int, data: dict, db: Session):
    user = db.query(User).filter(User.id == user_id).first()
    user.__dict__.update(data)
    db.commit()
```

Any key in `data` is assigned to the model instance.

### Safe

```python
def update_user(user_id: int, data: dict, db: Session):
    allowed_fields = {'email', 'first_name', 'last_name'}
    filtered_data = {k: v for k, v in data.items() if k in allowed_fields}
    user = db.query(User).filter(User.id == user_id).first()
    for key, value in filtered_data.items():
        setattr(user, key, value)
    db.commit()
```

An allowlist of permitted field names filters the input before
assignment.
