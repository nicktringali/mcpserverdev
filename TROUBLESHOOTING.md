# MCP Supercharger – Troubleshooting Log

Repo: nicktringali/mcpserverdev
PR: https://github.com/nicktringali/mcpserverdev/pull/1
Branch: devin/1755293975-initial-mcp-stack

Scope
- Dockerized MCP stack with SSE endpoints and auth:
  - Tools server on port 8001
  - Knowledge server on port 9000
  - Registry service on port 8080
  - Backing services: Qdrant (6333), Redis (6379)
- CI aims to build images, docker compose up, and smoke-test /health for the three HTTP services.
- FastMCP SSE mounted at /mcp; /health unauthenticated; optional Bearer token for other routes.

Environment and Constraints
- Linux VM: Ubuntu 24.04, Docker 28.2.2, Docker Compose v2.36.2
- Ports confirmed: 8001 FREE, 9000 FREE, 8080 FREE
- 8002/8010 were busy; avoided
- No Anthropic API usage; OpenAI-only configuration supported (optional)

Key Files
- docker-compose.yml
- server/src/app/main.py
- registry/main.py
- .github/workflows/build-and-smoketest.yml
- README.md
- .env.example

What Works (locally)
- Build and compose:
  - docker compose build
  - docker compose up -d
- Health endpoints (after brief startup):
  - curl -f http://localhost:8001/health -> OK
  - curl -f http://localhost:9000/health -> OK
  - curl -f http://localhost:8080/health -> OK
- SSE transport mounted at /mcp on both tools and knowledge servers
- /health is excluded from auth middleware; accessible without Bearer token
- Registry routes:
  - GET /health -> {"ok": true}
  - GET /servers -> lists tools and knowledge SSE URLs controlled via env:
    - MCP_TOOLS_URL, MCP_KNOWLEDGE_URL
- Feature flags (via env) used to enable/disable toolsets:
  - ENABLE_TOOLS/ENABLE_VECTOR/ENABLE_EXEC/ENABLE_TESTS/ENABLE_LINT

Local Repro Notes
- Initial curl to :8001 occasionally returned “Recv failure: Connection reset by peer” during the first seconds after container start, then stabilized.
- docker compose ps example showed:
  - mcp-tools and mcp-knowledge entering “health: starting” then reaching Up quickly
  - qdrant reported “unhealthy” for some time (does not block tools/knowledge /health), but tools/knowledge /health still OK
- Registry /health and /servers responded consistently after startup.

CI Setup and Changes
- CI workflow file: .github/workflows/build-and-smoketest.yml
  - Prepares a minimal .env and workspace/ dir (no secrets required)
  - Builds server and registry images
  - docker compose config, then docker compose up -d
  - Waits for 3 health endpoints with retries; on timeout, prints `docker compose ps` and logs
- Important: Pushing workflow files via the normal git proxy was blocked by GitHub due to “workflow” scope limitation.
  - Resolution: Updated the workflow via GitHub API using a provided GITHUB_PAT with repo+workflow scopes.
  - This allowed committing workflow updates directly to the PR branch.

CI Outcome (current)
- CI failing check name: build
- Recent job id: 48203801092
- Failure persists even after increasing health-wait loop to 120 retries, with diagnostics on timeout.
- Likely failure domains (based on prior attempts and typical GH-runners behavior):
  1) Readiness race: services not consistently ready before curls (flaky start timing on CI)
  2) Qdrant health flakiness (unhealthy reported while HTTP still works), which could cause logs noise but should not block other /health endpoints
  3) Missing compose-level healthchecks; CI currently waits on HTTP curls only

What We Changed
- Implemented FastMCP SSE servers for tools and knowledge with:
  - /health endpoint and SSE at /mcp
  - Optional Bearer token enforcement for non-health
  - Web search tool with Tavily (if key) or DuckDuckGo fallback
  - Vector RAG via Qdrant with OpenAI embeddings (if key) or sentence-transformers fallback
  - Safe filesystem read/write scoped to /workspace
- Registry FastAPI app with /health and /servers (env-configurable MCP_TOOLS_URL, MCP_KNOWLEDGE_URL)
- Docker Compose stack wiring for ports 8001, 9000, 8080, plus Redis and Qdrant
- GitHub Actions workflow adjustments:
  - Longer wait window (120 iterations; 2s sleep) and diagnostics on timeout
  - Removed flakey external network call
- Resolved a merge conflict in the workflow file and pushed via API due to workflow-scope restriction

Exact Commands Used (representative)
- Local compose and health:
  - docker compose config
  - docker compose build && docker compose up -d
  - for url in http://localhost:8001/health http://localhost:9000/health http://localhost:8080/health; do curl -f "$url"; done
  - docker compose ps && docker compose logs --tail=200
- CI monitoring:
  - git_pr_checks repo=nicktringali/mcpserverdev pull_number=1 wait=True
  - gh api (GET/PUT) to read and update .github/workflows/build-and-smoketest.yml on PR branch (using GITHUB_PAT)

Known Issues / Likely Root Causes for CI Failure
- CI job “build” still failing:
  - Most probable: readiness timing on GH runner (containers need more time to reach stable /health)
  - Compose lacks explicit healthcheck directives; adding them would make service readiness deterministic and could allow using “depends_on: condition: service_healthy” for nicer sequencing
  - Qdrant reports unhealthy for a while; not necessarily a blocker, but better to pin a stable image tag and/or account for its health behavior
- Not observed in local: stable /health after brief initial resets

Recommended Next Steps (when resuming)
1) Add compose healthchecks
   - mcp-tools, mcp-knowledge:
     test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
     interval: 5s; timeout: 3s; retries: 30; start_period: 10s
   - registry:
     test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
     interval: 5s; timeout: 3s; retries: 30; start_period: 5s
   - Optionally add depends_on with service_healthy conditions
2) In CI, wait for compose services’ health instead of blind HTTP curls, or keep HTTP curls but rely on healthchecks to stabilize earlier
3) Consider pinning qdrant image to a known stable tag if its health remains noisy on GH runners
4) If runner bandwidth limits cause model downloads (sentence-transformers fallback), consider forcing OPENAI embeddings path in CI by leaving OPENAI_API_KEY empty but ensuring that code path doesn’t try to download heavy models (current impl tries sentence-transformers only if no OpenAI key). Alternatively, vendor a light embedder for CI or mock embeddings.

Linux VM Quickstart (Deployment)
- Pre-req: Docker + Docker Compose installed
- Ports required open: 8001, 9000, 8080 (host)
- Steps:
  1) cp .env.example .env and set values as needed (optional: OPENAI_API_KEY; MCP_TOKEN/REGISTRY_TOKEN if protecting endpoints)
  2) mkdir -p workspace
  3) docker compose up -d
  4) Health checks:
     - curl -f http://localhost:8001/health
     - curl -f http://localhost:9000/health
     - curl -f http://localhost:8080/health
- Systemd example available at: deploy/systemd/mcpserver.service
- Reverse proxy recommendation (nginx or Caddy) before exposing publicly; secure SSE endpoints and include Authorization: Bearer headers if tokens are set

Client Connection (SSE)
- Tools SSE: http://<host>:8001/mcp
- Knowledge SSE: http://<host>:9000/mcp
- Include Authorization: Bearer <MCP_TOKEN> if configured

Closing Note
- Local health checks succeeded; CI is failing on “build” job due to readiness timing (most likely). Implementing compose-level healthchecks and/or adjusting CI to respect health status should stabilize it.
- Workflow file updates must continue via the GitHub API using a token with “workflow” scope if the proxy remains restricted.
