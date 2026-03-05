# Memory MCP Operations Runbook

This document is the operational source of truth for the current
memory-first architecture.

## Scope

The MCP server is intentionally minimal and should be used by Poke only for:

1) Pushing memory signals into the distiller queue.
2) Triggering memory recall briefs.

Anything else (admin, Notion editing tools, etc.) is intentionally out of scope.

## Current Architecture

### MCP server (`vm_server/`)

Only these tools are registered:

- `call_memory_distiller_daily`
- `call_memory_recall_brief_to_poke`

Source files:

- `vm_server/tools/memory_workflows.py`
- `vm_server/tools/registry.py`

### n8n workflows (`workflows/`)

- `Memory_Distiller_Daily.json`
  - production webhook path: `/n8n/webhook/memory-signal`
- `Memory_Recall_Brief_to_Poke.json`
  - production webhook path: `/n8n/webhook/memory-recall-brief`

Both workflows must be active in n8n for production webhooks to be registered.

## Required Runtime Configuration

### VM systemd service: `mcp-server.service`

The service must include (directly or via drop-in):

- `MEMORY_DISTILLER_WEBHOOK_URL`
- `MEMORY_SIGNAL_WEBHOOK_URL` (optional alias for compatibility)
- `MEMORY_RECALL_WEBHOOK_URL`
- `N8N_WEBHOOK_AUTH_HEADER`
- `N8N_WEBHOOK_AUTH_VALUE`

Recommended: keep these in a dedicated drop-in file:

- `/etc/systemd/system/mcp-server.service.d/memory.conf`

After edits:

```bash
sudo systemctl daemon-reload
sudo systemctl restart mcp-server.service
sudo systemctl is-active mcp-server.service
```

### n8n webhook auth

Both memory webhooks use credential `Header Auth account` (`httpHeaderAuth`).
MCP must send the same header name/value configured in this credential.

## Deployment and Sync Order

1) Push repo changes to `main` (deploy workflow updates VM code).
2) Run `N8N Workflow Sync` in `push` mode for memory workflows:
   - `Memory Distiller Daily`
   - `Memory Recall Brief to Poke`
3) Confirm webhooks are registered and protected:
   - `404` means workflow inactive or not synced.
   - `403 Authorization data is wrong!` means webhook exists but auth header mismatch.
4) Validate MCP tool calls (commands below).

## MCP Validation (Session-based)

FastMCP endpoint requires MCP session negotiation.

### Preferred helper

Use:

```bash
./vm/mcp_curl.sh --list
./vm/mcp_curl.sh call_memory_distiller_daily '{"event_text":"memory test"}'
./vm/mcp_curl.sh call_memory_recall_brief_to_poke '{"query":"books","limit":4}'
```

The helper auto-negotiates session (`initialize` + `notifications/initialized`)
when needed.

### Raw curl protocol flow

1) `initialize` and capture `mcp-session-id` response header.
2) Send `notifications/initialized` with that session id.
3) Send `tools/list` or `tools/call` with same session id.

## Expected Success Signals

- `tools/list` returns only the two memory tools.
- `call_memory_distiller_daily` returns:
  - `ok: true`
  - HTTP `200`
  - response preview includes queue metadata (`queued`, `pending_count`).
- `call_memory_recall_brief_to_poke` returns:
  - `ok: true`
  - HTTP `200`
  - response preview usually `{ "ok": true }`.

## Common Failure Modes

### `Bad Request: Missing session ID`

Cause: direct MCP call without protocol session.
Fix: use `vm/mcp_curl.sh` or full initialize flow.

### `MEMORY_DISTILLER_WEBHOOK_URL is not set` or `MEMORY_RECALL_WEBHOOK_URL is not set`

Cause: missing VM service environment variables.
Fix: update systemd env/drop-in and restart service.

### n8n `404 requested webhook ... is not registered`

Cause: workflow inactive or not synced.
Fix: set workflow `"active": true`, run n8n sync push.

### n8n `403 Authorization data is wrong!`

Cause: MCP header name/value does not match n8n `Header Auth account`.
Fix: align `N8N_WEBHOOK_AUTH_HEADER` and `N8N_WEBHOOK_AUTH_VALUE` with n8n credential.

## Change Checklist

When changing memory MCP behavior:

1) Update `vm_server/tools/memory_workflows.py`.
2) Confirm registry still registers only memory module.
3) Update:
   - `vm_server/README.md`
   - `docs/POKE_MEMORY_WORKFLOWS.md`
   - this runbook
4) Push to `main`.
5) Sync relevant n8n workflows.
6) Run concrete end-to-end MCP tests.
