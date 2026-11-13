import sys
from pathlib import Path

# Add 'mcp' directory to sys.path to avoid name collision with official 'mcp' SDK package
sys.path.insert(0, str(Path(__file__).resolve().parent))

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
import uvicorn

from config import settings
from prompts import register_all_prompts
from resources import register_all_resources
from server import mcp_server
from services import get_api_client
from tools import register_all_tools


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Lifespan context manager to handle startup and shutdown tasks."""
    # 1. Register all MCP components (tools, resources, prompts)
    register_all_tools(mcp_server)
    register_all_resources(mcp_server)
    register_all_prompts(mcp_server)

    # 2. Initialize Central API HTTP client session
    api_client = get_api_client()
    await api_client.start()

    yield

    # 3. Clean up Central API HTTP client session on shutdown
    await api_client.close()


app = FastAPI(
    title="OpenData MCP Server",
    description="MCP Server in FastAPI connecting to Central API",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check() -> dict:
    """Basic health check endpoint."""
    return {"status": "ok", "server": "OpenData MCP Server"}


# Mount the MCP SSE transport sub-application provided by FastMCP
app.mount("/mcp", mcp_server.sse_app())


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
