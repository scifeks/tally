# Python: Prototype pollution not applicable

Prototype pollution is a vulnerability class specific to languages with
prototype-based inheritance. Python is not vulnerable.

## Why Python is immune

Python uses class-based object-oriented programming with attribute
dictionaries (`__dict__`) for instance state. Objects do not have a
mutable prototype chain that can be modified to affect other instances.

When you modify an instance's attributes:

```python
user = {"role": "guest"}
user["role"] = "admin"
```

You are only modifying that instance's dictionary. Other instances are
not affected, even if they are instances of the same class.

## Related vulnerabilities in Python to watch for

While prototype pollution is not a concern, similar patterns in Python
may introduce other vulnerabilities:

- **Mutable default arguments**: `def process(config={}):` can allow
  state to persist across function calls. Use `None` and initialize
  on each call.
- **Module-level state mutation**: Modifying module-level dictionaries
  or objects can affect all code that imports that module. Be cautious
  when merging untrusted input into shared state.
- **Pickle deserialization**: `pickle.loads()` can execute arbitrary
  code. Never deserialize untrusted input.
- **Type confusion**: While Python does not have prototype pollution,
  type confusion via `__class__` or `__bases__` assignment can lead to
  unexpected behavior in some edge cases.

None of these are prototype pollution, but they warrant security
review in their own right.

## Scanning Python code

The `injection.prototype_pollution` scanner will not emit findings for
Python code because the vulnerability is impossible. If you see
recursive merge or deep assignment operations in Python, review them
for other vulnerabilities (state mutation, type confusion) instead.
