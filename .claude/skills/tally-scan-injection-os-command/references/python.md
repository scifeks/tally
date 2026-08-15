# Python OS command injection patterns

Vulnerable-vs-safe snippets for the Python subprocess and os module patterns
the `injection.os_command` scanner recognizes. When multiple safe forms exist,
the canonical one is shown first.

## os.system()

### Vulnerable

```python
user_filename = request.args.get("file")
os.system(f"rm {user_filename}")
os.system("ls " + user_directory)
os.system(f"cat {filepath}")
```

### Safe

```python
import subprocess
user_filename = request.args.get("file")
subprocess.run(["rm", user_filename])
```

`os.system()` always invokes the shell, making it inherently unsafe. Replace
with `subprocess.run()` using argument lists.

## os.popen()

### Vulnerable

```python
output = os.popen(f"grep {search_term} {filepath}").read()
result = os.popen("find " + directory).read()
```

### Safe

```python
import subprocess
result = subprocess.run(
    ["grep", search_term, filepath],
    capture_output=True,
    text=True,
)
output = result.stdout
```

`os.popen()` always invokes the shell. Use `subprocess.run()` with argument
lists.

## subprocess.call()

### Vulnerable

```python
import subprocess
user_path = request.args.get("path")
subprocess.call(f"ls {user_path}", shell=True)
subprocess.call("grep " + pattern, shell=True)
```

### Safe

```python
subprocess.call(["ls", user_path], shell=False)
subprocess.call(["grep", pattern], shell=False)
```

Never use `shell=True` with user-controlled input. Omitting `shell=True`
defaults to `shell=False`, which is safe.

## subprocess.Popen()

### Vulnerable

```python
proc = subprocess.Popen(
    f"ps aux | grep {search_term}",
    shell=True,
    stdout=subprocess.PIPE,
)
```

### Safe

```python
proc = subprocess.Popen(
    ["ps", "aux"],
    stdout=subprocess.PIPE,
    shell=False,
)
```

Do not use `shell=True`. Construct the command as a list of arguments.

## subprocess.run()

### Vulnerable

```python
user_url = request.args.get("url")
subprocess.run(f"curl {user_url}", shell=True)
subprocess.run("wget " + url, shell=True)
```

### Safe

```python
import subprocess
user_url = request.args.get("url")
subprocess.run(["curl", user_url], shell=False)
```

Pass arguments as a list. Never set `shell=True` with user input.

## subprocess.check_output()

### Vulnerable

```python
output = subprocess.check_output(f"echo {user_input}", shell=True)
```

### Safe

```python
output = subprocess.check_output(["echo", user_input], shell=False)
```

Same as `run()`: use argument lists and `shell=False`.

## Piped commands via subprocess

If you must pipe commands, use Python's logic instead of shell piping:

### Vulnerable

```python
result = subprocess.run(
    f"cat {filename} | grep {pattern}",
    shell=True,
    capture_output=True,
)
```

### Safe

```python
cat_result = subprocess.run(
    ["cat", filename],
    capture_output=True,
    text=True,
)
grep_result = subprocess.run(
    ["grep", pattern],
    input=cat_result.stdout,
    capture_output=True,
    text=True,
)
output = grep_result.stdout
```

Chain subprocess calls using stdin/stdout pipes without invoking the shell.

## shlex.quote() for single arguments

If you must construct a command string (not recommended), quote individual
arguments:

```python
import shlex
user_input = request.args.get("name")
safe_input = shlex.quote(user_input)
command = f"echo {safe_input}"
os.system(command)
```

This is a fallback only. Prefer `subprocess.run()` with argument lists.
