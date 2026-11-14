# TypeScript stored XSS patterns

Vulnerable-vs-safe snippets for TypeScript frameworks where
persistence-sourced data reaches HTML output. JavaScript patterns
from `references/javascript.md` apply on the Node runtime; this
file covers TypeScript-specific frameworks.

## Angular bypassSecurityTrustHtml

### Vulnerable

```typescript
import { DomSanitizer } from "@angular/platform-browser";

@Component({
  template: `<div [innerHTML]="trustedHtml"></div>`,
})
export class PostComponent implements OnInit {
  trustedHtml: SafeHtml;

  constructor(
    private sanitizer: DomSanitizer,
    private postService: PostService,
  ) {}

  ngOnInit() {
    this.postService.getPost(this.id).subscribe((post) => {
      this.trustedHtml =
        this.sanitizer.bypassSecurityTrustHtml(post.content);
    });
  }
}
```

### Safe

```typescript
@Component({
  template: `<div>{{ post.content }}</div>`,
})
export class PostComponent implements OnInit {
  post: Post;

  ngOnInit() {
    this.postService.getPost(this.id).subscribe((post) => {
      this.post = post;
    });
  }
}
```

Angular sanitizes `[innerHTML]` bindings by default. The
`bypassSecurityTrustHtml()` call disables sanitization. Remove
the bypass and use Angular's interpolation (`{{ }}`), which
escapes values. If HTML rendering is needed, let Angular's
built-in sanitizer handle it through `[innerHTML]` without the
bypass.

## React TSX dangerouslySetInnerHTML

### Vulnerable

```tsx
interface CommentProps {
  comment: { body: string };
}

function Comment({ comment }: CommentProps) {
  return (
    <div dangerouslySetInnerHTML={{ __html: comment.body }} />
  );
}
```

### Safe

```tsx
function Comment({ comment }: CommentProps) {
  return <div>{comment.body}</div>;
}
```

Same as JavaScript React. TypeScript type annotations do not
prevent `dangerouslySetInnerHTML` from rendering unsanitized
HTML. Remove it and render text directly.
