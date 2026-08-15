# JavaScript blind XSS patterns

Vulnerable-vs-safe snippets for JavaScript frameworks where
user-submitted data is stored and later rendered in admin or
internal contexts without escaping.

## Admin React dashboard

### Vulnerable

```jsx
function TicketDetail({ ticket }) {
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

```jsx
function TicketDetail({ ticket }) {
  return (
    <div className="admin-ticket">
      <h2>{ticket.subject}</h2>
      <div>{ticket.body}</div>
    </div>
  );
}
```

Admin components are high-value targets. Remove
`dangerouslySetInnerHTML` and render text directly. If HTML
rendering is needed, sanitize with `DOMPurify.sanitize()`.

## Internal tool with innerHTML

### Vulnerable

```javascript
async function loadFeedback(id) {
  const res = await fetch(`/api/admin/feedback/${id}`);
  const data = await res.json();
  document.getElementById("feedback-body").innerHTML =
    data.message;
}
```

### Safe

```javascript
async function loadFeedback(id) {
  const res = await fetch(`/api/admin/feedback/${id}`);
  const data = await res.json();
  document.getElementById("feedback-body").textContent =
    data.message;
}
```

Use `textContent` instead of `innerHTML`. Internal tools often
render data submitted by external users.

## Log viewer component

### Vulnerable

```jsx
function LogViewer({ entries }) {
  return (
    <table>
      {entries.map((entry) => (
        <tr key={entry.id}>
          <td
            dangerouslySetInnerHTML={{
              __html: entry.message,
            }}
          />
        </tr>
      ))}
    </table>
  );
}
```

### Safe

```jsx
function LogViewer({ entries }) {
  return (
    <table>
      {entries.map((entry) => (
        <tr key={entry.id}>
          <td>{entry.message}</td>
        </tr>
      ))}
    </table>
  );
}
```

Log entries often contain user-controlled data (usernames,
request paths, search queries). Render as text.

## Node email template

### Vulnerable

```javascript
const nodemailer = require("nodemailer");

async function notifyAdmin(ticket) {
  await transporter.sendMail({
    to: adminEmail,
    subject: "New support ticket",
    html: `<p>From: ${ticket.name}</p>
           <div>${ticket.body}</div>`,
  });
}
```

### Safe

```javascript
const escapeHtml = require("escape-html");

async function notifyAdmin(ticket) {
  await transporter.sendMail({
    to: adminEmail,
    subject: "New support ticket",
    html: `<p>From: ${escapeHtml(ticket.name)}</p>
           <div>${escapeHtml(ticket.body)}</div>`,
  });
}
```

Use the `escape-html` package for HTML email content, or use a
template engine with auto-escaping.
