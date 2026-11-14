# Python insecure deserialization patterns

Vulnerable-vs-safe snippets for the Python libraries the
`data_integrity.insecure_deserialization` scanner recognizes.

## pickle

### Vulnerable

```python
import pickle
from flask import request

data = request.get_json()
user = pickle.loads(data['payload'])

uploaded_file = request.files['data']
cached = pickle.load(uploaded_file)
```

### Safe

```python
import json
from flask import request

data = request.get_json()
user = json.loads(data['payload'])

import json
uploaded_file = request.files['data']
cached = json.load(uploaded_file)
```

pickle bytecode allows arbitrary code execution through the import statement
and function-call opcodes. There is no safe way to deserialize untrusted
pickle. Use JSON or msgspec for data exchange. For internal caching, sign
the pickle data with HMAC and verify the signature before deserializing.

## yaml (PyYAML)

### Vulnerable

```python
import yaml
from flask import request

config = yaml.load(request.data)

with open(user_config_path, 'r') as f:
    settings = yaml.load(f)
```

### Safe

```python
import yaml
from flask import request

config = yaml.safe_load(request.data)

with open(user_config_path, 'r') as f:
    settings = yaml.safe_load(f)
```

`yaml.load()` without a Loader argument allows Python object constructor
tags (`!!python/object`). Use `yaml.safe_load()` or pass `Loader=yaml.SafeLoader`
explicitly. SafeLoader only deserializes primitives and standard containers,
not arbitrary Python objects.

## marshal

### Vulnerable

```python
import marshal
from flask import request

code = marshal.loads(request.get_json()['bytecode'])
exec(code)
```

### Safe

```python
import json
from flask import request

code_str = request.get_json()['code']
code = compile(code_str, '<string>', 'exec')
exec(code)
```

`marshal.loads()` deserializes compiled Python code objects. Use only on
data the application itself marshaled. For user-supplied code, compile
from source after validating syntax.

## shelve

### Vulnerable

```python
import shelve
from flask import request

db_path = f"./cache/{request.args.get('db')}"
cache = shelve.open(db_path)
```

### Safe

```python
import shelve

db_path = "./cache/system_cache"
cache = shelve.open(db_path)
```

shelve is a persistent dictionary backed by pickle. Do not use a user-supplied
or user-influenced file path. shelve opens the file and deserializes its
contents, which may contain malicious pickle payloads created by an attacker.

## jsonpickle

### Vulnerable

```python
import jsonpickle
from flask import request

obj = jsonpickle.decode(request.get_json()['data'])
```

### Safe

```python
import json
from flask import request

data = json.loads(request.get_json()['data'])
```

jsonpickle is a JSON wrapper around pickle that includes Python type metadata.
Deserializing untrusted jsonpickle data is as unsafe as pickle. Use JSON and
validate the result against a schema (pydantic, marshmallow).

## dill

### Vulnerable

```python
import dill
from flask import request

func = dill.loads(request.get_json()['function'])
```

### Safe

```python
import json
from flask import request

code_str = request.get_json()['function']
code = compile(code_str, '<string>', 'eval')
func = eval(code)
```

dill is a more powerful alternative to pickle that serializes lambda functions
and code objects. Do not deserialize untrusted dill data. Use JSON for data
exchange and source validation for code.
