#!/usr/bin/env python3
import os
import sys
from pathlib import Path

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, rely on system env

from fastmcp import FastMCP

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from tools.registry import register_tools

mcp = FastMCP(
    "Lina Serendipity MCP Server",
    stateless_http=True,
)


# Optional health endpoint for external checks.
def _register_health_route(server: FastMCP) -> bool:
    app = getattr(server, "app", None)
    if app is None or not hasattr(app, "get"):
        return False

    @app.get("/health")
    async def health() -> dict:
        return {"ok": True}

    return True


_HAS_HEALTH_ROUTE = _register_health_route(mcp)
setattr(mcp, "_has_health_route", _HAS_HEALTH_ROUTE)

register_tools(mcp)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))

    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=port,
    )
