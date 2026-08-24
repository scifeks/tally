# TypeScript reflected XSS patterns

Vulnerable-vs-safe snippets for TypeScript frameworks where
same-request data reaches HTML output. JavaScript patterns from
`references/javascript.md` apply on the Node runtime; this file
covers TypeScript-specific frameworks.

## Express with typed request

### Vulnerable

```typescript
import { Request, Response } from "express";

app.get("/search", (req: Request, res: Response) => {
  const query = req.query.q as string;
  res.send(`<p>Results for: ${query}</p>`);
});
```

### Safe

```typescript
app.get("/search", (req: Request, res: Response) => {
  const query = req.query.q as string;
  res.render("search", { query });
});
```

TypeScript type annotations do not escape values. The `as string`
cast provides no XSS protection. Use a template engine with
auto-escaping.

## Angular route param to HTML

### Vulnerable

```typescript
import { ActivatedRoute } from "@angular/router";
import { DomSanitizer } from "@angular/platform-browser";

@Component({
  template: `<div [innerHTML]="greeting"></div>`,
})
export class GreetComponent implements OnInit {
  greeting: SafeHtml;

  constructor(
    private route: ActivatedRoute,
    private sanitizer: DomSanitizer,
  ) {}

  ngOnInit() {
    const name = this.route.snapshot.queryParamMap.get("name");
    this.greeting =
      this.sanitizer.bypassSecurityTrustHtml(
        `<p>Hello ${name}</p>`
      );
  }
}
```

### Safe

```typescript
@Component({
  template: `<div><p>Hello {{ name }}</p></div>`,
})
export class GreetComponent implements OnInit {
  name: string;

  ngOnInit() {
    this.name =
      this.route.snapshot.queryParamMap.get("name") ?? "";
  }
}
```

Angular interpolation (`{{ }}`) escapes values automatically.
Remove `bypassSecurityTrustHtml()` and use interpolation for
request-derived data.
