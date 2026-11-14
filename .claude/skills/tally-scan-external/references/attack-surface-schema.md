# Attack Surface Schema

Reference for the structured attack-surface specs produced by recon and consumed by domain agents. Three formats cover every input class: OpenAPI 3.1 for HTTP, AsyncAPI 3.0 for streaming channels, and a hardware YAML for serial, USB, and GPIO interfaces. All three share the `x-audit-*` extensions below.

## x-audit-* Extensions

| Extension | Applies to | Purpose |
|---|---|---|
| `x-audit-source` | operation, parameter, channel | Source location `file:line` in the codebase |
| `x-audit-sink` | parameter | Sink type and location where this input flows |
| `x-audit-sink-type` | parameter | One of 12 typed categories (see Typed Sink Categories) |
| `x-audit-validation` | parameter | Validation or sanitization applied before the sink |
| `x-audit-trust-boundary` | operation | Auth level required (`unauth`, `auth`, `admin`) |
| `x-audit-auth-discovered` | operation | Auth mechanisms discovered on this endpoint |
| `x-audit-dynamic-confirmed` | operation | Whether the endpoint was confirmed via live probe |
| `x-audit-cross-boundary` | parameter | Cross-component flow marker |
| `x-audit-no-params` | operation | Marks an endpoint that intentionally has no parameters |
| `x-audit-meta` | top-level info | Recon metadata (components mapped, auth phase, agent) |

### Value Conventions

| Extension | Value shape |
|---|---|
| `x-audit-source` | String `path/to/file.py:LINE` |
| `x-audit-sink` | String `<sink-type> at path/to/file.py:LINE` for the primary sink. When a parameter reaches multiple sinks, `x-audit-sink-type` carries all types as a list, and this field names the one with a traced location |
| `x-audit-sink-type` | List of sink category names. A parameter can reach more than one sink |
| `x-audit-validation` | String describing the check, or `none` when the value reaches the sink unchecked |
| `x-audit-trust-boundary` | One of `unauth`, `auth`, `admin` |
| `x-audit-auth-discovered` | List of mechanism names, for example `session-cookie`, `bearer-jwt`, `api-key-header`, `basic` |
| `x-audit-dynamic-confirmed` | Boolean. `false` when only static analysis located the endpoint |
| `x-audit-cross-boundary` | Object with `from`, `to`, and `via` (the call, queue, or RPC that crosses components) |
| `x-audit-no-params` | Boolean `true`. Set on operations that accept no user-supplied input (e.g. `GET /health`) |
| `x-audit-meta` | Object with `components`, `auth-phase`, and `agent` |

## OpenAPI 3.1 (HTTP Endpoints)

Every route becomes a path item. Every input (path, query, header, cookie, body field) becomes a parameter or a request body property. Extensions sit alongside standard OpenAPI fields.

```yaml
openapi: 3.1.0
info:
  title: target-app
  version: "0"
  x-audit-meta:
    components: [api, worker]
    auth-phase: post-auth
    agent: recon-mapper
paths:
  /api/v1/files/{name}:
    get:
      operationId: getFile
      x-audit-source: app/routes/files.py:42
      x-audit-trust-boundary: auth
      parameters:
        - name: name
          in: path
          required: true
          schema:
            type: string
          x-audit-source: app/routes/files.py:44
          x-audit-sink: file-path at app/services/storage.py:88
          x-audit-sink-type: [file-path]
          x-audit-validation: none
      responses:
        "200":
          description: File contents
```

Request body fields are documented under `requestBody.content.<type>.schema.properties`. Per-field extensions go on the property object using the same keys as parameters.

### Complete Example Operation

```yaml
paths:
  /api/v1/files/{name}:
    get:
      operationId: getFile
      summary: Download a stored file by name
      x-audit-source: app/routes/files.py:42
      x-audit-trust-boundary: auth
      x-audit-auth-discovered: [session-cookie, bearer-jwt]
      x-audit-dynamic-confirmed: true
      parameters:
        - name: name
          in: path
          required: true
          schema:
            type: string
          x-audit-source: app/routes/files.py:44
          x-audit-sink: file-path at app/services/storage.py:88
          x-audit-sink-type: [file-path]
          x-audit-validation: "strips leading slash only, no .. check (app/services/storage.py:80)"
        - name: format
          in: query
          required: false
          schema:
            type: string
            enum: [raw, base64]
          x-audit-source: app/routes/files.py:45
          x-audit-sink: template at app/routes/files.py:61
          x-audit-sink-type: [template]
          x-audit-validation: none
        - name: X-Tenant-Id
          in: header
          required: false
          schema:
            type: string
          x-audit-source: app/middleware/tenant.py:19
          x-audit-sink: sql at app/db/scoping.py:33
          x-audit-sink-type: [sql, log]
          x-audit-validation: none
          x-audit-cross-boundary:
            from: api
            to: worker
            via: "queue.enqueue('index_file') at app/routes/files.py:70"
      responses:
        "200":
          description: File contents
```

## AsyncAPI 3.0 (WebSocket, SockJS, Streaming)

Each connection endpoint is a `channel`. Each inbound message type is an `operation` with `action: receive` and a `message` payload. The same extensions apply: `x-audit-source` on channels, and the parameter-level extensions on message payload properties. Operation-level extensions go on the operation.

```yaml
asyncapi: 3.0.0
info:
  title: target-app-realtime
  version: "0"
  x-audit-meta:
    components: [gateway]
    auth-phase: post-auth
    agent: recon-mapper
servers:
  main:
    host: target.local:8080
    protocol: ws
channels:
  terminal:
    address: /ws/terminal
    x-audit-source: app/ws/terminal.py:12
    messages:
      runCommand:
        payload:
          type: object
          properties:
            cmd:
              type: string
              x-audit-source: app/ws/terminal.py:27
              x-audit-sink: shell at app/ws/terminal.py:31
              x-audit-sink-type: [shell]
              x-audit-validation: "allowlist of 5 command names (app/ws/terminal.py:24)"
operations:
  receiveRunCommand:
    action: receive
    channel:
      $ref: "#/channels/terminal"
    x-audit-source: app/ws/terminal.py:20
    x-audit-trust-boundary: auth
    x-audit-auth-discovered: [session-cookie]
    x-audit-dynamic-confirmed: false
```

Authentication on the upgrade request is recorded on the operation. Per-message authorization checks are recorded in `x-audit-validation` on the affected property.

## Hardware YAML (Serial, USB, GPIO)

OpenAPI and AsyncAPI have no vocabulary for device command protocols. Hardware interfaces use a custom schema that mirrors the same extension keys.

```yaml
hardware: 1
info:
  title: target-app-devices
  x-audit-meta:
    components: [device-daemon]
    auth-phase: pre-auth
    agent: recon-mapper
interfaces:
  - id: printer-serial
    kind: serial          # serial | usb | gpio | other
    device: /dev/ttyUSB0
    settings:
      baud: 115200
      framing: 8N1
    x-audit-source: daemon/printer.py:15
    x-audit-trust-boundary: unauth
    x-audit-dynamic-confirmed: false
    commands:
      - name: set_temperature
        direction: write  # write | read | bidirectional
        format: "M104 S{value}\n"
        x-audit-source: daemon/printer.py:58
        parameters:
          - name: value
            type: integer
            origin: /api/printer/temp   # upstream input that feeds this field
            x-audit-source: daemon/printer.py:55
            x-audit-sink: hardware at daemon/printer.py:60
            x-audit-sink-type: [hardware]
            x-audit-validation: "int() cast, no range check"
            x-audit-cross-boundary:
              from: api
              to: device-daemon
              via: "unix socket /run/daemon.sock"
```

| Field | Meaning |
|---|---|
| `kind` | `serial`, `usb`, `gpio`, or `other` |
| `device` | Device node, bus address, or pin identifier |
| `settings` | Transport parameters (baud, framing, USB endpoint, pin mode) |
| `commands[].format` | Wire format with `{param}` placeholders |
| `commands[].direction` | Whether the application writes to, reads from, or does both with the device |
| `parameters[].origin` | The upstream spec entry (HTTP route, channel) that supplies the value, when known |

For USB, `device` holds `vid:pid` and `settings` holds the endpoint addresses. For GPIO, `device` holds the pin number and `settings` holds mode (`in`, `out`, `pwm`) and edge triggers.

## Typed Sink Categories

`x-audit-sink-type` takes one or more of these 12 values. Patterns are search starting points, not an exhaustive list. Record a sink only when a request-derived value reaches it.

| Category | Meaning |
|---|---|
| `sql` | Query construction or execution |
| `shell` | OS command execution |
| `file-path` | Filesystem read, write, include, or path construction |
| `template` | Template rendering, code evaluation, or HTML output |
| `deserialize` | Object or data deserialization |
| `redirect` | HTTP redirect target |
| `header` | HTTP response header value |
| `hardware` | Serial, USB, or GPIO device access |
| `config` | Environment or configuration read that influences behavior |
| `auth` | Authentication, session, or credential handling |
| `log` | Log output |
| `network` | Outbound network request |

### sql

| Language | Patterns |
|---|---|
| Python | `cursor.execute()`, `engine.execute()`, `Model.objects.raw()`, `Model.objects.extra()`, f-string or `format()` in SQL |
| JS/TS | `query()`, `sequelize.query()`, `knex.raw()` |
| PHP | `mysqli_query()`, `PDO::query()`, `$wpdb->query()` |

### shell

| Language | Patterns |
|---|---|
| Python | `subprocess.run()`, `subprocess.Popen()`, `os.system()`, `os.popen()` |
| JS/TS | `child_process.exec()`, `child_process.spawn()` |
| PHP | `exec()`, `system()`, `shell_exec()`, `passthru()`, `proc_open()` |

### file-path

| Language | Patterns |
|---|---|
| Python | `open()`, `Path.read_text()`, `os.path.join()` with user input, `shutil.copy()` |
| JS/TS | `fs.readFile()`, `fs.writeFile()`, `path.join()` with user input |
| PHP | `file_get_contents()`, `fopen()`, `include()`, `require()` |

### template

| Language | Patterns |
|---|---|
| Python | `render_template_string()`, `Markup()`, `Template().render()`, Jinja2 `Environment()` |
| JS/TS | `eval()`, `innerHTML`, `document.write()`, template literals in HTML |
| PHP | `eval()`, `extract()`, Blade `{!! !!}` |

### deserialize

| Language | Patterns |
|---|---|
| Python | `pickle.loads()`, `yaml.load()` (unsafe loader), `marshal.loads()` |
| JS/TS | `JSON.parse()` in an eval context, `unserialize()` |
| PHP | `unserialize()`, `json_decode()` in an eval context |

### redirect

| Language | Patterns |
|---|---|
| Python | `redirect()`, `Response(status=302)` |
| JS/TS | `res.redirect()`, `window.location` |
| PHP | `header("Location: ...")` |

### header

| Language | Patterns |
|---|---|
| Python | `response.headers[]`, `make_response().headers` |
| JS/TS | `res.setHeader()`, `res.header()` |
| PHP | `header()` |

### hardware

| Language | Patterns |
|---|---|
| Python | `serial.Serial()`, `pyusb`, `RPi.GPIO` |
| JS/TS | `serialport`, `usb` |
| PHP | `dio_open()` |

### config

| Language | Patterns |
|---|---|
| Python | `os.environ[]`, `configparser`, `dotenv` |
| JS/TS | `process.env`, `dotenv` |
| PHP | `getenv()`, `$_ENV` |

### auth

| Language | Patterns |
|---|---|
| Python | `session[]`, `login_user()`, `check_password()` |
| JS/TS | `jwt.sign()`, `bcrypt.compare()`, `passport` |
| PHP | `$_SESSION`, `password_verify()`, `Auth::attempt()` |

### log

| Language | Patterns |
|---|---|
| Python | `logger.info()`, `logging.warning()` |
| JS/TS | `console.log()`, `winston` |
| PHP | `error_log()`, `Log::info()` |

### network

| Language | Patterns |
|---|---|
| Python | `requests.get()`, `urllib.request.urlopen()`, `httpx` |
| JS/TS | `fetch()`, `axios`, `http.get()` |
| PHP | `file_get_contents()` with a URL, `curl_exec()` |

## Partition Data Extraction

The orchestrator builds `${PARTITION_DATA}` for each domain agent from the merged spec files. The output is a plain text block, not YAML or JSON. Domain agents read it directly and do not parse it.

### Extraction Rules

- One block per partition, containing only that partition's files and the operations whose `x-audit-source` falls in those files.
- Every operation is listed. None are dropped or summarized.
- Every parameter carries its location, type, validation, and sink flows. Parameters with no sink are listed with `sinks: none`.
- Shared infrastructure nodes (middleware, auth helpers, DB wrappers) referenced by the partition's operations are listed once in their own section, even when they live outside the partition's files.
- Cross-boundary flows touching the partition are listed in their own section, in either direction.
- Operations from the AsyncAPI and hardware specs use the same layout. `METHOD path` becomes `CHANNEL address` or `DEVICE id`.

### Format

```text
PARTITION: files-api
FILES:
  app/routes/files.py
  app/services/storage.py

ENDPOINTS:
  GET /api/v1/files/{name}
    handler: getFile
    source: app/routes/files.py:42
    auth: auth (session-cookie, bearer-jwt)
    dynamic-confirmed: true
    parameters:
      name (path, string, required)
        source: app/routes/files.py:44
        validation: strips leading slash only, no .. check (app/services/storage.py:80)
        sinks: file-path at app/services/storage.py:88
      format (query, string, optional, enum: raw|base64)
        source: app/routes/files.py:45
        validation: none
        sinks: template at app/routes/files.py:61
      X-Tenant-Id (header, string, optional)
        source: app/middleware/tenant.py:19
        validation: none
        sinks: sql at app/db/scoping.py:33; log
        cross-boundary: api -> worker via queue.enqueue('index_file') at app/routes/files.py:70

  CHANNEL /ws/terminal
    handler: receiveRunCommand
    source: app/ws/terminal.py:20
    auth: auth (session-cookie)
    dynamic-confirmed: false
    parameters:
      cmd (message field, string)
        source: app/ws/terminal.py:27
        validation: allowlist of 5 command names (app/ws/terminal.py:24)
        sinks: shell at app/ws/terminal.py:31

SHARED INFRASTRUCTURE:
  app/middleware/tenant.py:19  tenant resolution from X-Tenant-Id, used by all routes in this partition
  app/db/scoping.py:33  tenant-scoped query builder

CROSS-BOUNDARY FLOWS:
  X-Tenant-Id: api -> worker via queue.enqueue('index_file') at app/routes/files.py:70
```

Field mapping from the merged spec:

| Text field | Spec source |
|---|---|
| `handler` | `operationId` |
| `source` | `x-audit-source` |
| `auth` | `x-audit-trust-boundary`, with `x-audit-auth-discovered` in parentheses |
| `dynamic-confirmed` | `x-audit-dynamic-confirmed` |
| parameter header line | `name`, `in`, `schema.type`, `required`, `schema.enum` |
| parameter `source` | parameter `x-audit-source` |
| `validation` | `x-audit-validation` |
| `sinks` | `x-audit-sink`, joined with `;`. Sink types without a location print the type alone |
| `cross-boundary` | `x-audit-cross-boundary` as `from -> to via <via>` |
