

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

MIT
