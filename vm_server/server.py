#!/usr/bin/env python3
"""
Lina Serendipity MCP Server
Production deployment for VM
"""
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

# Initialize the FastMCP server
mcp = FastMCP(
    "Lina Serendipity MCP Server",
)

# Create the ASGI application
# stateless_http=True enables HTTP mode without session management
app = mcp.http_app(stateless_http=True)

# Register all MCP tools
register_tools(mcp)

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    
    print("=" * 60)
    print("🚀 Starting Lina Serendipity MCP Server")
    print("=" * 60)
    print(f"Port: {port}")
    print(f"Transport: streamable-http")
    print(f"Host: 0.0.0.0 (accessible from all interfaces)")
    print("=" * 60)
    
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=port,
    )
