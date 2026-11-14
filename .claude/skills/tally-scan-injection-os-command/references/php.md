# PHP OS command injection patterns

Vulnerable-vs-safe snippets for the PHP command execution functions the
`injection.os_command` scanner recognizes. When multiple safe forms exist,
the canonical one is shown first.

## exec()

### Vulnerable

```php
$filename = $_GET['file'];
$output = exec("rm {$filename}");

$dir = request('directory');
exec("ls " . $dir);
```

### Safe

```php
$filename = $_GET['file'];
$escaped = escapeshellarg($filename);
$output = exec("rm {$escaped}");
```

Wrap each argument with `escapeshellarg()`. Better: refactor to use PHP
functions directly (`unlink()` instead of `exec('rm', ...)`).

## system()

### Vulnerable

```php
$dir = $_POST['directory'];
system("ls {$dir}");
```

### Safe

```php
$dir = $_POST['directory'];
system("ls " . escapeshellarg($dir));
```

Wrap user input with `escapeshellarg()` for each argument.

## passthru()

### Vulnerable

```php
$user_id = $_GET['id'];
passthru("grep {$user_id} /var/log/access.log");
```

### Safe

```php
$user_id = $_GET['id'];
passthru("grep " . escapeshellarg($user_id) . " /var/log/access.log");
```

Wrap each user-controlled argument with `escapeshellarg()`.

## shell_exec() and backtick operator

### Vulnerable

```php
$url = $_POST['url'];
$output = shell_exec("curl {$url}");

$domain = $request->input('domain');
$result = `ping -c 1 {$domain}`;
```

### Safe

```php
$url = $_POST['url'];
$output = shell_exec("curl " . escapeshellarg($url));

$domain = $request->input('domain');
$result = `ping -c 1 ` . escapeshellarg($domain);
```

Wrap user input with `escapeshellarg()` for every argument.

## proc_open()

### Vulnerable

```php
$filename = $_GET['file'];
$descriptorspec = array(
    0 => array("pipe", "r"),
    1 => array("pipe", "w"),
);
$process = proc_open("cat {$filename}", $descriptorspec, $pipes);
```

### Safe

```php
$filename = $_GET['file'];
$descriptorspec = array(
    0 => array("pipe", "r"),
    1 => array("pipe", "w"),
);
$process = proc_open(
    "cat " . escapeshellarg($filename),
    $descriptorspec,
    $pipes
);
```

Wrap user input with `escapeshellarg()` in the command string.

## popen()

### Vulnerable

```php
$pattern = $_POST['search'];
$handle = popen("grep {$pattern} /var/log/system.log", "r");
```

### Safe

```php
$pattern = $_POST['search'];
$handle = popen(
    "grep " . escapeshellarg($pattern) . " /var/log/system.log",
    "r"
);
```

Wrap user input with `escapeshellarg()`.

## escapeshellarg() vs. escapeshellcmd()

Use `escapeshellarg()` for individual arguments. Do NOT use
`escapeshellcmd()` on the entire command string.

### Wrong

```php
$userInput = $_GET['name'];
$cmd = escapeshellcmd("echo {$userInput}");
system($cmd);
```

`escapeshellcmd()` only escapes certain metacharacters and is not
sufficient for command injection defense.

### Correct

```php
$userInput = $_GET['name'];
system("echo " . escapeshellarg($userInput));
```

Wrap each argument individually with `escapeshellarg()`.

## Refactoring to built-in functions

The safest approach is to avoid shell execution entirely:

### Before (using shell)

```php
$filename = $_POST['file'];
$content = shell_exec("cat {$filename}");
```

### After (using PHP functions)

```php
$filename = $_POST['file'];
if (!preg_match('/^[a-z0-9._-]+$/i', $filename)) {
    throw new InvalidArgumentException("Invalid filename");
}
$content = file_get_contents("./uploads/{$filename}");
```

Use PHP's built-in file and system functions whenever possible.
