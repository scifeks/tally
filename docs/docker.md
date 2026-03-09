# Security Audit Containers

Two persistent containers exposing `composer audit` and `npm audit` to a host application via `docker exec` are provided for convenience. 
You don't have to use them. If you use them, make sure to configure them during tool config in the `./tally` app.

## Structure

```
.
├── docker-compose.yaml.example # Copy to docker-compose.yaml
├── Dockerfile.php        # php:8.3-cli-alpine + Composer 2
└── Dockerfile.node       # ubuntu:24.04 + nvm + Node LTS
```

---

## Setup
### 1. Copy example docker-compose.yaml
`cp docker-compose.yaml.example docker-compose.yaml`

### 2. Configure volume mounts

Edit `docker-compose.yaml` and add a volume entry for each repo:

```yaml
volumes:
  - "/host/path/to/repo:/internal/mount/point:ro"
```

### 3. Build and start the containers

```bash
docker compose build
docker compose up -d
```

The containers will stay running in the background and wait for commands.

---

## Usage

The host app executes audits by calling `docker exec` with the internal working directory and tool path it has configured:

```bash
# npm audit
docker exec -w <repo.docker_path> <container_name> <tool_path> audit --json

# composer audit
docker exec -w <repo.docker_path> <container_name> <tool_path> audit --format=json
```

### Concrete examples

```bash
docker exec -w /repos/my-node-app node-auditor /home/auditor/.local/bin/npm audit --json

docker exec -w /repos/my-php-app php-auditor /usr/bin/composer audit --format=json
```

### Tool paths

| Container      | Tool       | Path                            |
|----------------|------------|---------------------------------|
| `php-auditor`  | composer   | `/usr/bin/composer`             |
| `node-auditor` | npm        | `/home/auditor/.local/bin/npm`  |

---

## Customisation

### Change Node.js version at build time

```bash
docker compose build --build-arg NODE_VERSION=22 node-auditor
```

### Stop the containers

```bash
docker compose down
```