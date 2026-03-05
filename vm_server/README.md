# VM MCP Server

This folder contains the MCP server code deployed to the VM at
`/home/ubuntu/mcp-server-template/src`.

Current design is intentionally minimal: the server exposes only two tools,
both used to trigger your n8n memory workflows for Poke.

## Exposed tools

1) `call_memory_distiller_daily`
- Sends a memory signal to the `memory-signal` webhook.
- Use when Poke wants to store a memory signal for later distillation.

2) `call_memory_recall_brief_to_poke`
- Triggers the `memory-recall-brief` webhook.
- Use when Poke wants a compact recall summary.

## Required env vars on VM

- `MEMORY_DISTILLER_WEBHOOK_URL`
  - Example: `https://mcp-lina.duckdns.org/n8n/webhook/memory-signal`
  - Backward-compatible alias: `MEMORY_SIGNAL_WEBHOOK_URL`
- `MEMORY_RECALL_WEBHOOK_URL`
  - Example: `https://mcp-lina.duckdns.org/n8n/webhook/memory-recall-brief`

Optional webhook auth header:
- `N8N_WEBHOOK_AUTH_HEADER` (default: `Authorization`)
- `N8N_WEBHOOK_AUTH_VALUE` (header value sent to both webhook calls)

## Quick checks

List tools:
```bash
curl -sS https://mcp-lina.duckdns.org/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

Call distiller signal tool:
```bash
curl -sS https://mcp-lina.duckdns.org/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"call_memory_distiller_daily","arguments":{"event_text":"Jordane switched from book A to book B","tags":["books"],"confidence":0.82}}}'
```

Call recall brief tool:
```bash
curl -sS https://mcp-lina.duckdns.org/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"call_memory_recall_brief_to_poke","arguments":{"query":"books","limit":6}}}'
```
