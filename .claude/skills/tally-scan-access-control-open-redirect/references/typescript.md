# TypeScript open redirect patterns

Vulnerable-vs-safe snippets for TypeScript web frameworks the
`access_control.open_redirect` scanner recognizes. Node patterns
also apply; see `javascript.md` for additional examples.

## NestJS

### Vulnerable

```typescript
import { Controller, Get, Query, Redirect } from '@nestjs/common';

@Controller('auth')
export class AuthController {
    @Get('login')
    @Redirect()
    login(@Query('next') next: string) {
        return { url: next };
    }
}

@Controller('app')
export class AppController {
    @Post('go')
    go(@Body('returnUrl') url: string, @Res() res: Response) {
        res.redirect(url);
    }
}
```

### Safe

```typescript
import { Controller, Get, Query, Redirect } from '@nestjs/common';

const ALLOWED_HOSTS = ['example.com', 'app.example.com'];

function isAllowedRedirect(url: string): boolean {
    try {
        const parsed = new URL(url);
        return ALLOWED_HOSTS.includes(parsed.hostname || '');
    } catch (e) {
        return false;
    }
}

@Controller('auth')
export class AuthController {
    @Get('login')
    @Redirect()
    login(@Query('next') next: string) {
        if (next && isAllowedRedirect(next)) {
            return { url: next };
        }
        return { url: '/dashboard' };
    }
}

@Controller('app')
export class AppController {
    @Post('go')
    go(@Body('returnUrl') url: string, @Res() res: Response) {
        if (url && isAllowedRedirect(url)) {
            res.redirect(url);
        } else {
            res.redirect('/dashboard');
        }
    }
}
```

For the `@Redirect()` decorator, validate the URL before returning
it. For manual `res.redirect()`, use `new URL()` to validate the
destination's host.

## Fastify

### Vulnerable

```typescript
import Fastify from 'fastify';

const app = Fastify();

app.get('/login', async (req, reply) => {
    const next = req.query.redirect as string;
    reply.redirect(next);
});
```

### Safe

```typescript
import Fastify from 'fastify';

const app = Fastify();
const ALLOWED_HOSTS = ['example.com', 'app.example.com'];

function isAllowedRedirect(url: string): boolean {
    try {
        const parsed = new URL(url);
        return ALLOWED_HOSTS.includes(parsed.hostname || '');
    } catch (e) {
        return false;
    }
}

app.get('/login', async (req, reply) => {
    const next = req.query.redirect as string;
    if (next && isAllowedRedirect(next)) {
        reply.redirect(next);
    } else {
        reply.redirect('/dashboard');
    }
});
```

Always validate the redirect destination before passing it to
`reply.redirect()`.

## Remix

### Vulnerable

```typescript
import { redirect } from '@remix-run/node';

export async function loader({ request }: LoaderArgs) {
    const referer = request.headers.get('referer');
    if (referer) {
        throw redirect(referer);
    }
    return null;
}

export async function action({ request }: ActionArgs) {
    const url = new URL(request.url).searchParams.get('next');
    if (url) {
        throw redirect(url);
    }
    return null;
}
```

### Safe

```typescript
import { redirect } from '@remix-run/node';

const ALLOWED_HOSTS = ['example.com', 'app.example.com'];

function isAllowedRedirect(url: string): boolean {
    try {
        const parsed = new URL(url);
        return ALLOWED_HOSTS.includes(parsed.hostname || '');
    } catch (e) {
        return false;
    }
}

export async function loader({ request }: LoaderArgs) {
    return null;
}

export async function action({ request }: ActionArgs) {
    const url = new URL(request.url).searchParams.get('next');
    if (url && isAllowedRedirect(url)) {
        throw redirect(url);
    }
    throw redirect('/dashboard');
}
```

Validate the redirect destination before throwing a Remix `redirect()`.
Check the parsed URL's hostname against an allowlist.

## Relative-path-only redirect (safe)

```typescript
import { Controller, Get, Query, Redirect } from '@nestjs/common';

const ALLOWED_PAGES = ['home', 'about', 'contact'];

@Controller('pages')
export class PageController {
    @Get('go')
    @Redirect()
    goToPage(@Query('page') page: string) {
        const safePage = ALLOWED_PAGES.includes(page) ? page : 'home';
        return { url: `/${safePage}` };
    }
}
```

Redirects to relative paths that start with `/` are safe if the
path segment is validated against an allowlist.

## Anti-pattern: calling URL constructor in a try-catch that ignores
## the result

```typescript
app.get('/login', async (req, reply) => {
    const url = req.query.next as string;
    try {
        new URL(url);
    } catch (e) {
        // Log and continue
        console.error('Invalid URL:', e);
    }
    reply.redirect(url);
});
```

The URL is validated but the result is ignored and the redirect
proceeds anyway. Always use the validation result to decide whether
to redirect.
