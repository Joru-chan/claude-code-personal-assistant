# VM MCP Server

This folder contains the MCP server code deployed to the VM at
`/home/ubuntu/mcp-server-template/src`.

The server is memory-only by design. It exposes exactly two tools for Poke.

Detailed operations/runbook:

- `docs/MEMORY_MCP_OPERATIONS.md`

## Exposed tools

1) `call_memory_distiller_daily`
- Sends a memory signal to the `memory-signal` webhook.

2) `call_memory_recall_brief_to_poke`
- Triggers the `memory-recall-brief` webhook.

## Required VM env vars

- `MEMORY_DISTILLER_WEBHOOK_URL`
  - Example: `https://mcp-lina.duckdns.org/n8n/webhook/memory-signal`
- `MEMORY_SIGNAL_WEBHOOK_URL`
  - Optional compatibility alias for distiller URL.
- `MEMORY_RECALL_WEBHOOK_URL`
  - Example: `https://mcp-lina.duckdns.org/n8n/webhook/memory-recall-brief`
- `N8N_WEBHOOK_AUTH_HEADER`
  - Header name expected by n8n webhook auth credential.
- `N8N_WEBHOOK_AUTH_VALUE`
  - Header value expected by n8n webhook auth credential.

## Quick checks

Use the helper from `vm/` (it handles MCP session negotiation):

```bash
./vm/mcp_curl.sh --list
./vm/mcp_curl.sh call_memory_distiller_daily '{"event_text":"memory smoke test"}'
./vm/mcp_curl.sh call_memory_recall_brief_to_poke '{"query":"books","limit":4}'
```
