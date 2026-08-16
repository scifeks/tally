# PHP mass assignment patterns

Vulnerable-vs-safe snippets for the PHP frameworks the
`access_control.mass_assignment` scanner recognizes.

## Laravel Eloquent without $fillable

### Vulnerable

```php
<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class User extends Model
{
    // No $fillable or $guarded defined
}

// In controller:
$user = User::create($request->all());

$user->fill($request->all())->save();
```

An attacker can set any column: `is_admin`, `role`, `verified_at`, etc.

### Safe

```php
<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class User extends Model
{
    protected $fillable = ['name', 'email', 'password'];

    protected $guarded = ['id', 'is_admin', 'created_at', 'updated_at'];
}

// In controller:
$user = User::create($request->only(['name', 'email', 'password']));

$user->update($request->only(['name', 'email']));
```

`$fillable` explicitly whitelists fields users can set. Alternatively,
`$guarded` blacklists fields that cannot be mass-assigned. Use
`$request->only()` to filter input before passing to the model.

## Laravel without explicit field filtering

### Vulnerable

```php
<?php

class UserController extends Controller
{
    public function store(Request $request)
    {
        $user = User::create($request->all());
        return $user;
    }

    public function update(Request $request, User $user)
    {
        $user->fill($request->all())->save();
        return $user;
    }
}
```

`$request->all()` includes every key from the request, including
attacker-injected fields.

### Safe

```php
<?php

class UserController extends Controller
{
    public function store(Request $request)
    {
        $validated = $request->validate([
            'name' => 'required|string',
            'email' => 'required|email|unique:users',
        ]);
        $user = User::create($validated);
        return $user;
    }

    public function update(Request $request, User $user)
    {
        $validated = $request->validate([
            'name' => 'string',
            'email' => 'email|unique:users',
        ]);
        $user->update($validated);
        return $user;
    }
}
```

Use `$request->validate()` to filter input and then pass only validated
fields. Alternatively, use `$request->only()`:

```php
$user = User::create($request->only(['name', 'email']));
```

## Symfony form handling

### Vulnerable

```php
<?php

class UserController extends AbstractController
{
    #[Route('/users', methods: ['POST'])]
    public function create(Request $request, EntityManagerInterface $em): Response
    {
        $user = new User();
        $form = $this->createForm(UserType::class, $user);
        $form->submit($request->request->all());

        if ($form->isValid()) {
            $em->persist($user);
            $em->flush();
        }
    }
}
```

If the form is built without explicit field restrictions, all request
data is mapped to the User entity.

### Safe

```php
<?php

class UserType extends AbstractType
{
    public function buildForm(FormBuilderInterface $builder, array $options): void
    {
        $builder
            ->add('name', TextType::class)
            ->add('email', EmailType::class);
    }

    public function configureOptions(OptionsResolver $resolver): void
    {
        $resolver->setDefaults([
            'data_class' => User::class,
        ]);
    }
}

class UserController extends AbstractController
{
    #[Route('/users', methods: ['POST'])]
    public function create(Request $request, EntityManagerInterface $em): Response
    {
        $user = new User();
        $form = $this->createForm(UserType::class, $user);
        $form->handleRequest($request);

        if ($form->isSubmitted() && $form->isValid()) {
            $em->persist($user);
            $em->flush();
        }
    }
}
```

Explicitly define which fields the form accepts in the form class.
Symfony's form builder only maps fields that are declared.
