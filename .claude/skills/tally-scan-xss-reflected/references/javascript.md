# JavaScript reflected XSS patterns

Vulnerable-vs-safe snippets for JavaScript frameworks where
same-request or URL-sourced data reaches HTML output. When
multiple safe forms exist, the canonical one is shown first.

## Express res.send

### Vulnerable

```javascript
app.get("/search", (req, res) => {
  res.send("<p>Results for: " + req.query.q + "</p>");
});
```

### Safe

```javascript
app.get("/search", (req, res) => {
  res.render("search", { query: req.query.q });
});
```

Use a template engine with auto-escaping (EJS `<%= %>`, Pug,
Handlebars `{{ }}`). If building strings directly, use the
`escape-html` package.

## EJS unescaped output

### Vulnerable

```ejs
<p>Search: <%- req.query.search %></p>
```

### Safe

```ejs
<p>Search: <%= req.query.search %></p>
```

EJS `<%= %>` escapes HTML entities. `<%- %>` outputs raw HTML.
Use `<%= %>` for request-sourced data.

## Client-side DOM with URL data

### Vulnerable

```javascript
const params = new URLSearchParams(location.search);
document.getElementById("output").innerHTML = params.get("q");

document.write(location.hash.slice(1));

document.getElementById("ref").innerHTML = document.referrer;
```

### Safe

```javascript
const params = new URLSearchParams(location.search);
document.getElementById("output").textContent = params.get("q");
```

Use `textContent` instead of `innerHTML` for URL-derived data.
`location.search`, `location.hash`, `document.referrer`, and
`location.pathname` are attacker-controllable in reflected XSS
scenarios.

## Client-side document.write

### Vulnerable

```javascript
const msg = new URLSearchParams(location.search).get("msg");
document.write("<p>" + msg + "</p>");
```

### Safe

```javascript
const msg = new URLSearchParams(location.search).get("msg");
const p = document.createElement("p");
p.textContent = msg;
document.body.appendChild(p);
```

`document.write()` parses its argument as HTML. Use DOM APIs
for safe element construction.
