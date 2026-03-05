from __future__ import annotations

from fastmcp import FastMCP

from tools import memory_workflows


def register_tools(mcp: FastMCP) -> None:
    """Register the minimal MCP toolset."""
    for module in (memory_workflows,):
        module.register(mcp)
