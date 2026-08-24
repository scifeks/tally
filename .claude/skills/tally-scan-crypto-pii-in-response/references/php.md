# PHP PII in response patterns

Vulnerable and safe snippets for PHP API response handling the
`crypto.pii_in_response` scanner recognizes.

## Eloquent model without $hidden

### Vulnerable

```php
class User extends Model
{
    protected $fillable = [
        'name', 'email', 'password', 'ssn',
    ];
}

return response()->json(User::find($id));
```

### Safe

```php
class User extends Model
{
    protected $hidden = [
        'password', 'remember_token', 'ssn',
    ];
}
```

The `$hidden` array prevents sensitive fields from appearing in JSON
serialization.

## Laravel API Resource

### Vulnerable

```php
class UserResource extends JsonResource
{
    public function toArray($request)
    {
        return parent::toArray($request);
    }
}
```

### Safe

```php
class UserResource extends JsonResource
{
    public function toArray($request)
    {
        return [
            'id' => $this->id,
            'name' => $this->name,
            'email' => $this->email,
        ];
    }
}
```

`parent::toArray()` includes every model attribute. List only the fields
the API consumer needs.

## Controller returning full model

### Vulnerable

```php
public function show(User $user)
{
    return $user;
}
```

### Safe

```php
public function show(User $user)
{
    return new UserResource($user);
}
```

Return a Resource or explicitly select fields instead of relying on
implicit model serialization.
