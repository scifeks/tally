# JavaScript stored XSS patterns

Vulnerable-vs-safe snippets for JavaScript frameworks where
persistence-sourced data reaches HTML output. When multiple safe
forms exist, the canonical one is shown first.

## DOM innerHTML

### Vulnerable

```javascript
const response = await fetch("/api/comments/" + id);
const data = await response.json();
document.getElementById("comment").innerHTML = data.body;
```

### Safe

```javascript
document.getElementById("comment").textContent = data.body;
```

`textContent` sets plain text and never parses HTML. Use
`textContent` for user-sourced data. If HTML structure is needed,
parse with a sanitizer first:

```javascript
import DOMPurify from "dompurify";
element.innerHTML = DOMPurify.sanitize(data.body);
```

## DOM insertAdjacentHTML

### Vulnerable

```javascript
const items = await fetchStoredItems();
items.forEach((item) => {
  list.insertAdjacentHTML("beforeend", `<li>${item.name}</li>`);
});
```

### Safe

```javascript
items.forEach((item) => {
  const li = document.createElement("li");
  li.textContent = item.name;
  list.appendChild(li);
});
```

`insertAdjacentHTML()` parses the string as HTML. Use DOM APIs
(`createElement`, `textContent`, `appendChild`) for safe element
construction.

## React dangerouslySetInnerHTML

### Vulnerable

```jsx
function Comment({ comment }) {
  return (
    <div dangerouslySetInnerHTML={{ __html: comment.body }} />
  );
}
```

### Safe

```jsx
function Comment({ comment }) {
  return <div>{comment.body}</div>;
}
```

React escapes string values in JSX expressions by default.
`dangerouslySetInnerHTML` bypasses this. Remove it and render
text directly. If HTML rendering is needed, sanitize first:

```jsx
import DOMPurify from "dompurify";
<div
  dangerouslySetInnerHTML={{
    __html: DOMPurify.sanitize(comment.body),
  }}
/>
```

## EJS templates (Express)

### Vulnerable

```ejs
<div class="post-body"><%- post.body %></div>
<p><%- comment.text %></p>
```

### Safe

```ejs
<div class="post-body"><%= post.body %></div>
<p><%= comment.text %></p>
```

EJS `<%= %>` escapes HTML entities. `<%- %>` outputs raw HTML.
Use `<%= %>` for all user-sourced data.

## Handlebars

### Vulnerable

```handlebars
<div class="content">{{{post.content}}}</div>
```

### Safe

```handlebars
<div class="content">{{post.content}}</div>
```

Handlebars `{{ }}` escapes by default. Triple braces `{{{ }}}`
output raw HTML. Use double braces for user-sourced data.
