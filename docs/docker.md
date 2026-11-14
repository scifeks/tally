# Docker Tool Execution

Tally supports Docker execution for any security scanning tool configured with `"location": "docker"` in `config/commands.json`. Tools running in Docker execute via `docker exec` inside a user-provided container with access to your repository code.

## Supported Tools

The following tools have Docker wrapper support. You can run any of these inside a container by setting `"location": "docker"` in `config/commands.json` and providing the container name and mount path.

- composer-audit
- gitleaks
- graphql-cop
- npm-audit
- nuclei
- osv-scanner
- php-psalm
- pip-audit
- semgrep
- xsstrike
- zap

---

## Pre-Built Convenience Containers

Two optional Docker containers are provided for `npm audit` and `composer audit`. They are not required, but if you use them, configure them during tool setup in the Tally REPL.

### Structure

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

## Configuration Fields

When you configure a tool to run in Docker, you must specify two fields for each repository:

**container_name.** The name of a running Docker container as shown by `docker ps`. This is the container where the tool will execute. Use the `tool add` REPL command to set the tool path once, then the `repo add` command to set `container_name` and `docker_path` for each repository.

**docker_path.** The mount path where your repository is accessible inside the container. For example, if you run `docker run -v /host/repo:/internal/app my-container`, set `docker_path` to `/internal/app`.

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

## Customization

### Change Node.js version at build time

```bash
docker compose build --build-arg NODE_VERSION=22 node-auditor
```

### Stop the containers

```bash
docker compose down
```

---

## AI Triage Containers

Tally also uses Docker containers for AI-driven triage operations. See [docs/triage.md](triage.md) for setup and configuration of triage-specific containers.