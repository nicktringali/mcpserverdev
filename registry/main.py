import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()

MCP_TOOLS_URL = os.getenv("MCP_TOOLS_URL", "http://mcp-tools:8000")
MCP_KNOWLEDGE_URL = os.getenv("MCP_KNOWLEDGE_URL", "http://mcp-knowledge:8000")
REGISTRY_TOKEN = os.getenv("REGISTRY_TOKEN")

@app.get("/health")
async def health():
    return JSONResponse({"ok": True})

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if request.url.path not in ("/", "/health"):
        if REGISTRY_TOKEN:
            auth = request.headers.get("authorization") or request.headers.get("Authorization")
            if not auth or not auth.lower().startswith("bearer ") or auth.split(" ", 1)[1] != REGISTRY_TOKEN:
                return JSONResponse({"error": "unauthorized"}, status_code=401)
    return await call_next(request)

@app.get("/servers")
async def servers():
    return JSONResponse({
        "servers": [
            {"name": "mcp-tools", "url": MCP_TOOLS_URL, "transport": "sse"},
            {"name": "mcp-knowledge", "url": MCP_KNOWLEDGE_URL, "transport": "sse"},
        ]
    })
