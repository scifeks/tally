# PHP template injection patterns

Vulnerable-vs-safe snippets for the PHP template engines the
`injection.template` scanner recognizes. When multiple safe forms exist,
the canonical one is shown first.

## Twig

### Vulnerable

```php
<?php
$twig = new \Twig\Environment(new \Twig\Loader\FilesystemLoader('templates'));

// Dangerous: user input becomes template source
$template = $twig->createTemplate($userInput);
echo $template->render(['name' => $userName]);

// Also dangerous
$source = $_GET['template'];
$template = $twig->createTemplate($source);
echo $template->render();
```

### Safe

```php
<?php
$twig = new \Twig\Environment(
    new \Twig\Loader\FilesystemLoader('templates')
);

// Load from file only
$template = $twig->load('profile.html');
echo $template->render(['name' => $userName]);

// Or use render()
echo $twig->render('profile.html', ['name' => $userName]);
```

Twig templates should always be loaded from files. The loader enforces
a filesystem boundary. Never create templates from request data.

## Laravel Blade

### Vulnerable

```php
<?php
use Illuminate\Support\Facades\Blade;

// User input compiled as Blade template
$compiled = Blade::compileString($_GET['content']);
echo $compiled;

// Or inline blade compilation
$template = <<<'EOT'
<?php echo "{{ $userInput }}"; ?>
EOT;
eval(Blade::compileString($template));
```

### Safe

```php
<?php
// Use Blade template files
return view('myview', ['userInput' => $userInput]);

// In resources/views/myview.blade.php:
// <p>{{ $userInput }}</p>
// Blade automatically escapes unless you use {!! !!}
```

Store Blade templates as files in `resources/views/`. Use `view()` to
render them. Blade escapes variables by default unless you use `{!! !!}`
syntax, which should only be used for trusted content.

## Smarty

### Vulnerable

```php
<?php
$smarty = new Smarty();

// String prefix with user input
$template_source = 'string:' . $_GET['content'];
$smarty->display($template_source);

// Or direct string assignment
$smarty->assign('name', $userName);
$smarty->display('string:Hello {$name}!');
```

### Safe

```php
<?php
$smarty = new Smarty();
$smarty->setTemplateDir('./templates');
$smarty->setCacheDir('./cache');

// Load from file only
$smarty->assign('name', $userName);
$smarty->display('hello.tpl');

// Or render to string
$output = $smarty->fetch('hello.tpl');
```

Smarty should load templates from the filesystem only. Do not use the
`string:` prefix with user-controlled data. Set explicit template and
cache directories, and validate all file paths.
