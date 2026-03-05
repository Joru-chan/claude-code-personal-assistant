# Poke Memory Workflows (n8n + Notion)

This repository now includes two workflows:

- `workflows/Memory_Distiller_Daily.json`
- `workflows/Memory_Recall_Brief_to_Poke.json`

They are designed to improve Poke memory quality by keeping a dedicated Notion memory database fresh and by pushing a compact recall brief to Poke.

## 1) Notion Database Schema

Create a Notion database for memories with the exact property names below:

- `Name` (Title)
- `memory_key` (Rich text)
- `type` (Select)
- `summary` (Rich text)
- `confidence` (Number)
- `last_seen` (Date)
- `stale_after_days` (Number)
- `status` (Select)
: Suggested values: `active`, `outdated`
- `source` (Rich text)
- `tags` (Multi-select)

These names are used directly in workflow JSON bodies for Notion API calls.

## 2) Workflow Behavior

### Memory Distiller Daily

- Ingestion endpoint: `POST /n8n/webhook/memory-signal`
- Signals are queued in workflow static data.
- Daily at 08:00, queued signals are distilled into up to 10 memory candidates.
- Upsert logic:
  - Query by `memory_key`
  - Create page if missing
  - Update page if existing
- Sends summary to Poke using the existing webhook pattern.

If your MCP server is configured with
`MEMORY_DISTILLER_WEBHOOK_URL` (or `MEMORY_SIGNAL_WEBHOOK_URL`), calls to
`call_memory_distiller_daily` send signals directly into this queue.

### Memory Recall Brief to Poke

- Recall endpoint: `POST /n8n/webhook/memory-recall-brief`
- Also runs daily at 09:00 (and supports manual trigger).
- Queries active memories from Notion.
- Marks stale rows in the message when `ageDays > stale_after_days`.
- Sends a compact recall brief to Poke.

## 3) Required Configuration in n8n

Both workflows use these values in `Set ... Config` nodes:

- `notion_token`
- `memory_db_id`

Current default values are placeholders:

- `REPLACE_WITH_NOTION_TOKEN`
- `REPLACE_WITH_NOTION_MEMORY_DB_ID`

You can replace them in-node, or provide env vars:

- `NOTION_TOKEN`
- `NOTION_MEMORY_DB_ID`

## 4) Security

Both webhook triggers are protected with existing `Header Auth account` credentials.

## 5) Test Payloads

### Capture memory signal

```bash
curl -X POST "https://mcp-lina.duckdns.org/n8n/webhook/memory-signal" \
  -H "Content-Type: application/json" \
  -H "Authorization: <your webhook header auth>" \
  -d '{
    "event_text": "I stopped reading Atomic Habits and started a sci-fi novel last week",
    "source": "poke",
    "confidence": 0.82,
    "tags": ["books", "habit_change"]
  }'
```

### Request recall brief

```bash
curl -X POST "https://mcp-lina.duckdns.org/n8n/webhook/memory-recall-brief" \
  -H "Content-Type: application/json" \
  -H "Authorization: <your webhook header auth>" \
  -d '{
    "query": "books",
    "limit": 6
  }'
```

## 6) Poke Send Pattern

Both workflows send to Poke through:

- `POST https://poke.com/api/v1/inbound-sms/webhook`
- `authentication: genericCredentialType`
- `genericAuthType: httpBearerAuth`
- Body field: `message`

This matches the existing pattern used in your current workflows.
