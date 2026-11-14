# TypeScript blind XSS patterns

Vulnerable-vs-safe snippets for TypeScript frameworks where
user-submitted data is stored and later rendered in admin or
internal contexts without escaping. JavaScript patterns from
`references/javascript.md` apply on the Node runtime; this file
covers TypeScript-specific frameworks.

## Angular admin component

### Vulnerable

```typescript
import { DomSanitizer } from "@angular/platform-browser";

@Component({
  template: `
    <div class="admin-ticket">
      <h2>{{ ticket.subject }}</h2>
      <div [innerHTML]="trustedBody"></div>
    </div>
  `,
})
export class AdminTicketComponent implements OnInit {
  ticket: Ticket;
  trustedBody: SafeHtml;

  constructor(
    private sanitizer: DomSanitizer,
    private ticketService: TicketService,
  ) {}

  ngOnInit() {
    this.ticketService.getTicket(this.id).subscribe((t) => {
      this.ticket = t;
      this.trustedBody =
        this.sanitizer.bypassSecurityTrustHtml(t.body);
    });
  }
}
```

### Safe

```typescript
@Component({
  template: `
    <div class="admin-ticket">
      <h2>{{ ticket.subject }}</h2>
      <div>{{ ticket.body }}</div>
    </div>
  `,
})
export class AdminTicketComponent implements OnInit {
  ticket: Ticket;

  ngOnInit() {
    this.ticketService.getTicket(this.id).subscribe((t) => {
      this.ticket = t;
    });
  }
}
```

Remove `bypassSecurityTrustHtml()` in admin components. Angular
interpolation (`{{ }}`) escapes values. Admin interfaces are
high-value targets for blind XSS because they run in privileged
sessions.

## React admin dashboard (TSX)

### Vulnerable

```tsx
interface TicketProps {
  ticket: { subject: string; body: string };
}

function AdminTicketView({ ticket }: TicketProps) {
  return (
    <div className="admin-ticket">
      <h2>{ticket.subject}</h2>
      <div
        dangerouslySetInnerHTML={{ __html: ticket.body }}
      />
    </div>
  );
}
```

### Safe

```tsx
function AdminTicketView({ ticket }: TicketProps) {
  return (
    <div className="admin-ticket">
      <h2>{ticket.subject}</h2>
      <div>{ticket.body}</div>
    </div>
  );
}
```

Same as JavaScript React. TypeScript types do not prevent
`dangerouslySetInnerHTML` from rendering unsanitized HTML.
Admin dashboards processing user-submitted data are prime
blind XSS targets.
