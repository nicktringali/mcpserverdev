import os


import json


from typing import Any, Dict, List, Optional





import anyio


from dotenv import load_dotenv


from pydantic import BaseModel, Field





from fastapi import FastAPI, Request


from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from sentence_transformers import SentenceTransformer

from openai import OpenAI

from duckduckgo_search import DDGS

try:
    from tavily import TavilyClient
except Exception:
    TavilyClient = None  # type: ignore

from mcp.server import Server
from mcp.server.sse import run as run_sse
from mcp.server.stdio import run as run_stdio

load_dotenv()

MCP_SERVER_HOST = os.getenv("MCP_SERVER_HOST", "0.0.0.0")
MCP_SERVER_PORT = int(os.getenv("MCP_SERVER_PORT", "8000"))
WORKSPACE_DIR = os.getenv("WORKSPACE_DIR", "/workspace")

QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY") or None

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or None
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY") or None

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MCP_TOKEN = os.getenv("MCP_TOKEN")

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if request.url.path not in ("/", "/health", "/debug/web_search"):
        if MCP_TOKEN:
            auth = request.headers.get("authorization") or request.headers.get("Authorization")
            if not auth or not auth.lower().startswith("bearer ") or auth.split(" ", 1)[1] != MCP_TOKEN:
                return JSONResponse({"error": "unauthorized"}, status_code=401)
    return await call_next(request)

@app.get("/health")
async def health():
    return JSONResponse({"ok": True})

SERVER_NAME = os.getenv("SERVER_NAME", "mcp-supercharger")
ENABLE_TOOLS = os.getenv("ENABLE_TOOLS", "1") not in ("0", "false", "False")
ENABLE_VECTOR = os.getenv("ENABLE_VECTOR", "1") not in ("0", "false", "False")

server = Server(SERVER_NAME)

class AddTextPayload(BaseModel):
    collection: str
    text: str
    id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class QueryPayload(BaseModel):
    collection: str
    query: str
    top_k: int = 5

def _ensure_workspace_path(path: str) -> str:
    p = os.path.abspath(os.path.join(WORKSPACE_DIR, path))
    if not p.startswith(os.path.abspath(WORKSPACE_DIR) + os.sep) and p != os.path.abspath(WORKSPACE_DIR):
        raise ValueError("Path escapes workspace")
    return p

def get_qdrant() -> QdrantClient:
    return QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

def get_embedder():
    if OPENAI_API_KEY:
        client = OpenAI(api_key=OPENAI_API_KEY)
        def embed(texts: List[str]) -> List[List[float]]:
            resp = client.embeddings.create(model="text-embedding-3-small", input=texts)
            return [d.embedding for d in resp.data]
        return embed
    else:
        model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        def embed(texts: List[str]) -> List[List[float]]:
            return model.encode(texts, convert_to_numpy=False).tolist()
        return embed

def get_search():
    if TAVILY_API_KEY and TavilyClient is not None:
        tclient = TavilyClient(api_key=TAVILY_API_KEY)
        def search(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
            out = tclient.search(query=query, max_results=max_results)
            return out if isinstance(out, list) else out.get("results", [])
        return search
    else:
        def search(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    results.append({
                        "title": r.get("title"),
                        "url": r.get("href"),
                        "snippet": r.get("body"),
                        "source": "duckduckgo"
                    })
            return results
        return search

@server.tool()
async def web_search(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    s = get_search()
    return s(query, max_results=max_results)

@server.tool()
async def add_text(collection: str, text: str, id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    embed = get_embedder()
    vec = embed([text])[0]
    client = get_qdrant()
    dim = len(vec)
    try:
        client.get_collection(collection_name=collection)
    except Exception:
        client.recreate_collection(
            collection_name=collection,
            vectors_config=qmodels.VectorParams(size=dim, distance=qmodels.Distance.COSINE),
        )
    point_id = id or os.urandom(8).hex()
    client.upsert(
        collection_name=collection,
        points=[qmodels.PointStruct(id=point_id, vector=vec, payload={"text": text, **(metadata or {})})],
    )
    return {"ok": True, "id": point_id, "collection": collection}

@app.get("/debug/web_search")
async def debug_web_search(query: str, max_results: int = 3):
    s = get_search()
    return JSONResponse(s(query, max_results=max_results))

@server.tool()
async def query(collection: str, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    embed = get_embedder()
    qvec = embed([query])[0]
    client = get_qdrant()
    try:
        res = client.search(
            collection_name=collection,
            query_vector=qvec,
            with_payload=True,
            limit=top_k
        )
    except Exception:
        return []
    out: List[Dict[str, Any]] = []
    for p in res:
        out.append({
            "id": str(p.id),
            "score": p.score,
            "payload": p.payload,
        })
    return out

@server.tool()
async def read_file(path: str) -> str:
    p = _ensure_workspace_path(path)
    if not os.path.exists(p):
        raise FileNotFoundError("File not found")
    with open(p, "r", encoding="utf-8") as f:
        return f.read()

@server.tool()
async def write_file(path: str, content: str, overwrite: bool = False) -> Dict[str, Any]:
    p = _ensure_workspace_path(path)
    if os.path.exists(p) and not overwrite:
        raise FileExistsError("File exists; set overwrite=True to replace")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)
    return {"ok": True, "path": p}

@app.get("/")
async def info():
    return JSONResponse({"name": "mcp-supercharger", "transport": "sse", "health": "/health"})

if __name__ == "__main__":
    transport = os.getenv("TRANSPORT", "sse").lower()
    if transport == "stdio":
        anyio.run(run_stdio, server)
    else:
        anyio.run(run_sse, server, MCP_SERVER_HOST, MCP_SERVER_PORT, app)
