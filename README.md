

# MCP Supercharger

A Dockerized, production-ready Model Context Protocol (MCP) server to supercharge AI models with:
- Web search (Tavily or DuckDuckGo fallback)
- Vector knowledge base (Qdrant)
- Filesystem tools (safe read/write within a mounted workspace)
- Optional Postgres and Redis
- SSE over HTTP transport for MCP clients that support it

This repository provides:
- docker-compose.yml for local/production-like deployment
- A Python MCP server (mcp-python SDK) exposing multiple tools
- .env.example for configuration and API keys
- Workspace volume for mounting your data
- Healthchecks and resource considerations

## Features
## GitHub Actions CI: enabling workflows

If you see “refusing to allow an OAuth App to create or update workflow .github/workflows/... without workflow scope”, you have two options:

1) Quick manual add
- Create the directory .github/workflows in the repo
- Add the workflow file build-and-smoketest.yml there (from this PR or the attached file)
- Commit to the repo. Actions will run automatically on PRs/main after that.

2) Enable permissions so automation can push workflows
- If using a GitHub App (recommended):
  - Org Settings → Installed GitHub Apps → find your app (e.g., Devin AI Integration) → Configure
  - Permissions: set Actions to Read and write
  - Repository access: grant access to nicktringali/mcpserverdev (or All repositories)
  - Save
- If using a PAT (classic):
  - GitHub → Settings → Developer settings → Personal access tokens (classic) → Generate new token
  - Scopes: repo and workflow
  - Update your integration to use this token for pushes

After enabling, we’ll re-push .github/workflows/build-and-smoketest.yml to enable CI.


- Web Search:


  - Uses Tavily API if TAVILY_API_KEY is set
  - Falls back to DuckDuckGo search (no API key) for basic results
- Vector Store:
  - Qdrant for embeddings search and storage
  - Embeddings via OpenAI if OPENAI_API_KEY is set
  - Otherwise, uses sentence-transformers (all-MiniLM-L6-v2)
- Filesystem:
  - Read/write text files within a confined /workspace directory (mounted from host)
- MCP Transport:
  - SSE server exposed on port 8000 for HTTP-based MCP clients

## Quick Start

1) Copy environment example and edit values:
   cp .env.example .env
   - Set TAVILY_API_KEY and/or OPENAI_API_KEY if you have them
   - Adjust Qdrant/Redis/Postgres settings if needed

2) Create a local workspace directory:
   mkdir -p ./workspace

3) Start services:
   docker compose up --build

4) Services:
   - Tools server SSE: http://localhost:8001
   - Knowledge server SSE: http://localhost:9000
   - Registry: http://localhost:8080
   - Qdrant: http://localhost:6333
   - Redis: redis://localhost:6379
   - Postgres: localhost:5432

5) Connect from an MCP-compatible client:
   - Tools server SSE: http://localhost:8001
## Transports

- SSE/HTTP: default. Set TRANSPORT=sse (default).
- stdio: set TRANSPORT=stdio to run in stdio mode (no HTTP).

## Feature Flags

- ENABLE_TOOLS: enable general-purpose tools (web_search, fs ops)
- ENABLE_VECTOR: enable Qdrant-backed RAG tools
- ENABLE_EXEC: allow exec_cmd and pip_install
- ENABLE_TESTS: allow run_pytest
- ENABLE_LINT: allow run_ruff and run_mypy

## Deployment (Linux VM)

- Ensure Docker and Docker Compose are installed.
- Create workspace directory and copy .env from .env.example, set OPENAI_API_KEY.
- Start: docker compose up -d
- Health: curl -f http://localhost:8001/health and http://localhost:9000/health

Optional systemd unit example (edit paths as needed):

[Unit]
Description=MCP Server Stack
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
WorkingDirectory=/opt/mcpserverdev
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
RemainAfterExit=yes
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target

Registry listing: http://localhost:8080/servers

Note: Depending on your client, you may need to configure an MCP “server” entry using the SSE endpoint with any required headers (none by default).

## Environment Variables

See .env.example for full list. Highlights:
- OPENAI_API_KEY: optional, enable OpenAI embeddings
- TAVILY_API_KEY: optional, enable Tavily search
- QDRANT_URL, QDRANT_API_KEY: Qdrant connection
- POSTGRES_*: Optional Postgres variables, not strictly required
- REDIS_URL: Optional

## Docker Compose

docker-compose.yml includes:
- mcp-server: Python 3.12 + Poetry, mcp-python, SSE server on 8000
- qdrant: Vector DB on 6333
- redis: Redis cache on 6379
- postgres: Postgres on 5432 (disabled by default if you comment it out)

Data volumes:
- ./workspace mounted to /workspace in the container
- Named volume for Qdrant

## Tools Exposed

- web_search(query: str, max_results: int = 5) -> list
- add_text(collection: str, text: str, id: str = None, metadata: dict = None) -> dict
- query(collection: str, query: str, top_k: int = 5) -> list
- read_file(path: str) -> str
- write_file(path: str, content: str, overwrite: bool = False) -> dict
## Example MCP client configs

These target the SSE endpoints. If you set MCP_TOKEN in .env, include the Authorization header.

Tools SSE (port 8001):
- URL: http://localhost:8001/mcp
- Headers (if protected): Authorization: Bearer &lt;MCP_TOKEN&gt;

Knowledge SSE (port 9000):
- URL: http://localhost:9000/mcp
- Headers (if protected): Authorization: Bearer &lt;MCP_TOKEN&gt;

### stdio mode (local dev)
Set TRANSPORT=stdio and run the app directly (no HTTP). For example:
- docker compose exec mcp-tools sh
- export TRANSPORT=stdio
- python -m app.main

Your MCP client should connect to the process stdio streams. For Dockerized SSE/HTTP, leave TRANSPORT unset (default: sse).

Note: WebSocket transport can be added later; SSE endpoints are mounted at /mcp and work with current MCP clients that support HTTP/SSE.


All filesystem operations are sandboxed to /workspace to prevent access outside the mounted directory.

## Production Notes

- Use docker compose with proper resource limits
- Put an nginx or Caddy reverse proxy in front of :8000 if exposing publicly
- Secure the SSE endpoint with an auth proxy or mutual TLS when exposing to the internet
- Consider setting QDRANT__SERVICE__GRPC_PORT disabled unless needed
- Back up Qdrant volume
- Monitor service logs via docker compose

## Roadmap

- Add a gateway/bridge service to aggregate multiple MCP servers
- Optional auth middleware for SSE
- Add more domain tools (e.g., database query tool using Postgres)

## License
## CI details and troubleshooting

- The GitHub Actions workflow auto-generates a minimal .env and a workspace/ directory so that docker compose can run in CI without secrets.
- Health checks: CI waits for these to respond with 2xx before proceeding:
  - http://localhost:8001/health
  - http://localhost:9000/health
  - http://localhost:8080/health
- The CI workflow avoids external network calls to prevent flakiness on GitHub-hosted runners.

Troubleshooting:
- If CI fails at docker compose config: ensure a .env exists. In CI this is created; locally run: cp .env.example .env and edit values.
- If health checks time out: check docker compose logs, especially the mcp-tools and mcp-knowledge services, and verify that ports 8001 and 9000 are not conflicting on the runner/host.
- If embedding import errors occur: the server lazily imports sentence-transformers only when OpenAI embeddings are not configured. Set OPENAI_API_KEY to use OpenAI embeddings, or ensure the container can download the model on first run.



MIT
