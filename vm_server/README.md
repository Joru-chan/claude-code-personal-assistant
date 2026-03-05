# VM MCP Server

This folder contains the exact server code deployed to the VM at
`/home/ubuntu/mcp-server-template/src`.

## Adding a new tool
1) Create a module in `vm_server/tools/` with a `register(mcp: FastMCP)` function.
2) Decorate tool functions with `@mcp.tool` inside `register`.
3) Import the module in `vm_server/tools/registry.py` and add it to the list.

Example skeleton:
```python
from fastmcp import FastMCP

def register(mcp: FastMCP) -> None:
    @mcp.tool
    def my_tool() -> dict:
        return {"summary": "ok", "result": {}, "next_actions": [], "errors": []}
```

## Test hello tool (remote)
```bash
curl -sS https://mcp-lina.duckdns.org/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"hello","arguments":{"name":"Jordane"}}}'
```

## Tool Requests (Notion)
Required env vars on the VM service:
- `NOTION_TOKEN`
- `TOOL_REQUESTS_DB_ID`

Latest items:
```bash
curl -sS https://mcp-lina.duckdns.org/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"tool_requests_latest","arguments":{"limit":10,"statuses":["new","triaging"]}}}'
```

Search by keyword:
```bash
curl -sS https://mcp-lina.duckdns.org/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"tool_requests_search","arguments":{"query":"calendar","limit":10}}}'
```

Safety: read-only tools (no writes).

## Mood memory bridge
`create_mood_memory` now forwards to:

- Legacy mood webhook (Google Sheet pipeline): `MOOD_MEMORY_WEBHOOK_URL`
- New memory distiller pipeline: `MEMORY_SIGNAL_WEBHOOK_URL`

Set both on the VM service if you want dual-write behavior.

## Pantry inventory (Receipt photo)
Required env vars on the VM service:
- `NOTION_TOKEN`
- `PANTRY_DB_ID`

Optional property mapping env vars (defaults in code):
- `PANTRY_PROP_NAME`
- `PANTRY_PROP_QUANTITY`
- `PANTRY_PROP_UNIT`
- `PANTRY_PROP_CATEGORY`
- `PANTRY_PROP_PURCHASE_DATE`
- `PANTRY_PROP_STORE`

Usage (dry-run preview):
```bash
curl -sS https://mcp-lina.duckdns.org/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"receipt_photo_pantry_inventory","arguments":{"receipt_text":"2x Milk $6.00\nApples $4.99","store":"Monoprix","purchase_date":"2026-01-16","dry_run":true}}}'
```

## Health check
- Primary: MCP JSON-RPC via `/mcp` (for example `tools/list`).
- Optional: `GET /health` only if provided by your reverse proxy/infrastructure.
- Fallback: call the `health_check` tool via `/mcp`.
