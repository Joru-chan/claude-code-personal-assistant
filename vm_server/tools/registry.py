from __future__ import annotations

from fastmcp import FastMCP

from tools import (
    admin,
    basic,
    health,
    hello,
    mood,
    notion_editor,
    photo_of_physical_items_like_kitchen_stuff,
    receipt_photo_pantry_inventory,
    serendipity,
    system_overview,
    tool_requests,
    weather,
)


def register_tools(mcp: FastMCP) -> None:
    """Register all MCP tools with the server."""
    for module in (
        admin,
        basic,
        mood,
        serendipity,
        system_overview,
        hello,
        tool_requests,
        notion_editor,
        health,
        photo_of_physical_items_like_kitchen_stuff,
        receipt_photo_pantry_inventory,
        weather,
    ):
        module.register(mcp)
