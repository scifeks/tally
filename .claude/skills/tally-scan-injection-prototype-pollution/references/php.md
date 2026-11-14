# PHP: Prototype pollution not applicable

Prototype pollution is a vulnerability class specific to languages with
prototype-based inheritance. PHP is not vulnerable.

## Why PHP is immune

PHP uses class-based object-oriented programming. Objects are instances
of classes with fixed, declared properties. PHP does not have a
mutable prototype chain that can be modified to affect other instances.

When you set a property on an instance:

```php
$user = new User();
$user->role = 'admin';
```

You are only setting that instance's property. Other instances of the
same class are not affected. Properties are tied to the class
definition, not to a shared prototype.

Even if you use dynamic properties (magic methods like `__set`), each
instance has its own property store. Modifying one instance does not
affect others.

## Related vulnerabilities in PHP to watch for

While prototype pollution is not a concern, similar patterns in PHP
may introduce other vulnerabilities:

- **Object injection via unserialize()**: `unserialize()` can
  instantiate arbitrary classes and trigger `__wakeup()` or
  `__destruct()` methods with attacker-controlled state. Never
  unserialize untrusted input.
- **Magic method abuse**: `__get()`, `__set()`, `__call()` can be
  exploited if they lack proper validation. Always validate input to
  these methods.
- **Variable variables**: `$$var` with user input can lead to
  arbitrary variable assignment. Use explicit allowlists or avoid the
  pattern entirely.
- **Mutation of static properties**: `self::$shared = $user_input;`
  can affect all subsequent code. Be cautious with static state.

None of these are prototype pollution, but they warrant security
review in their own right.

## Scanning PHP code

The `injection.prototype_pollution` scanner will not emit findings for
PHP code because the vulnerability is impossible. If you see recursive
merge or object mutation patterns in PHP, review them for other
vulnerabilities (object injection, variable variables, static state
mutation) instead.
