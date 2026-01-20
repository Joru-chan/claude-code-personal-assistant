# Codex Setup Checklist

This file documents how to run this assistant from the terminal using Codex CLI.

## Quick Start (3 steps)

1. **Install prerequisites:**
   ```bash
   # Install Codex CLI
   npm i -g @openai/codex
   
   # Install Python 3.10+ and create venv (optional)
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Configure environment:**
   ```bash
   # Copy template and fill in your values
   cp .env.template .env
   # Edit .env with your NOTION_TOKEN
   ```

3. **Verify setup:**
   ```bash
   python3 scripts/verify_setup.py
   ```

That's it! See below for detailed MCP integration setup.

---

## Detailed Setup Instructions

### 1) Review Documentation
- [ ] Read `AGENT_GUIDE.md` for workflows and responsibilities
- [ ] Check `PERSONAL_CONTEXT.md` for database IDs and configuration

### 2) Prerequisites
- [ ] Install Codex CLI: `npm i -g @openai/codex`
- [ ] Install Node.js
- [ ] Install Python 3.13+ and `uv` (required by `mcp-gsuite-enhanced`)
- [ ] (Optional) Copy `.env.example` to `.env` for local scripts only.
- [ ] (Optional) Create a venv for local scripts:
  - `python3 -m venv venv`
  - `source venv/bin/activate`
  - `pip install -r requirements.txt`

### 2.5) Universal Router (scripts/agent.py)
This is the single entrypoint for natural language requests.

- List or search tool requests:
  - `python scripts/agent.py "show tool requests"`
  - `python scripts/agent.py "search wishes for calendar conflicts"`
- Pick what to build next:
  - `python scripts/agent.py "what should we build next?"`
- Scaffold a new tool (writes files, requires `--execute`):
  - `python scripts/agent.py "start a new project from my wishes" --execute`
- Deploy to VM (writes, requires `--execute`):
  - `python scripts/agent.py "deploy latest changes to the VM" --execute`

### 3) Notion MCP (`notion-mcp`)
- [ ] Set the token in your shell (local only, do not commit):
  - `export NOTION_TOKEN="paste_token_here"`
- [ ] Add the MCP server (config stored in `~/.codex/config.toml`, shared by CLI + IDE):
  - If you use `nvm`, point PATH at the Node 20+ bin to avoid shell init output:
    - `codex mcp add notion-mcp --env NOTION_TOKEN="$NOTION_TOKEN" -- env PATH="$HOME/.nvm/versions/node/v20.20.0/bin:$PATH" npx -y @notionhq/notion-mcp-server`
  - Otherwise (Node 20+ already on PATH):
    - `codex mcp add notion-mcp --env NOTION_TOKEN="$NOTION_TOKEN" -- npx -y @notionhq/notion-mcp-server`
- [ ] Test:
  - `codex mcp list`
  - `codex exec "List my Notion databases"`
- [ ] Ensure the Life Atlas database is shared with the integration (used as the personal taxonomy).

### 4) Tool Requests / Friction Log backlog (Notion)

This backlog captures friction points and automation ideas. Preferred location: under the Life Atlas “Assistant HQ” page.

### Schema
- Title (title)
- Description (rich_text)
- Desired outcome (rich_text)
- Frequency (select): once / weekly / daily / many-times-per-day
- Impact (select): low / medium / high
- Domain (multi_select): email, calendar, notion, health, errands, planning, admin, relationships, home, finance, other
- Status (select): new / triaging / spec-ready / building / shipped / won't-do
- Source (select): poke / terminal / other
- Created time (created_time)
- Last updated time (last_edited_time)
- Link(s) (url)
- Notes / constraints (rich_text)

### Create via Codex (MCP)
Run from this repo root and use the Assistant HQ page ID from `CONTEXT.md`:
```bash
codex exec "Create a Notion database named 'Tool Requests / Friction Log' under page_id <ASSISTANT_HQ_PAGE_ID> with properties: Title (title), Description (rich_text), Desired outcome (rich_text), Frequency (select: once, weekly, daily, many-times-per-day), Impact (select: low, medium, high), Domain (multi_select: email, calendar, notion, health, errands, planning, admin, relationships, home, finance, other), Status (select: new, triaging, spec-ready, building, shipped, won't-do), Source (select: poke, terminal, other), Created time (created_time), Last updated time (last_edited_time), Link(s) (url), Notes / constraints (rich_text). Return the database ID and URL."
```

### Create manually (Notion UI)
1. Open the Life Atlas “Assistant HQ” page in Notion.
2. Add a new database named “Tool Requests / Friction Log”.
3. Add the properties listed in the schema above (matching names and types).
4. Share the database with the Notion integration.
5. Record the database ID and URL in `CONTEXT.md`.

### Quick add from terminal
This is the canonical capture interface (terminal + Poke). It writes to Notion via MCP and falls back to a local queue if MCP is unavailable.

- Set the DB ID once (local only, optional if `CONTEXT.md` is filled in):
  - `export TOOL_REQUESTS_DB_ID="paste_db_id_here"`
- Minimal capture (one-liner complaint):
  - `python scripts/capture_tool_request.py "Annoyed by calendar invite spam"`
- Full capture:
  - `python scripts/capture_tool_request.py "Annoyed by calendar invite spam" --desired-outcome "Auto-filter spammy invites" --domain "calendar,email" --frequency daily --impact medium`

### Offline mode (queue)
- If MCP is down, entries are queued at `memory/tool_requests_queue.jsonl`.
- Flush later:
  - `python scripts/flush_tool_requests_queue.py`

### Smoke test
- List five most recent entries:
  - `codex exec "List the 5 most recent items from the Tool Requests / Friction Log database <TOOL_REQUESTS_DB_ID> and show Title, Status, Frequency, Impact, and Created time."`
- Create a test entry, then archive it:
  - `python scripts/capture_tool_request.py "Test item - delete" --desired-outcome "verify capture works" --domain "other" --source terminal`
  - `codex exec "Find the most recent Tool Requests entry with title 'Test item - delete' and archive it."`

### Weekly triage (review + propose)
- Read-only run (writes nothing):
  - `python scripts/triage_tool_requests.py`
- Apply run (updates Status from new -> triaging):
  - `python scripts/triage_tool_requests.py --apply`
- Adjust scoring weights:
  - `python scripts/triage_tool_requests.py --impact-weight 1.0 --frequency-weight 1.5 --recency-weight 0.5`
- Output:
  - Report saved to `memory/triage/YYYY-MM-DD.md`

### Calendar Hygiene Assistant (tool prototype)
- Generate a plan (read-only):
  - `python tools/calendar_hygiene/calendar_hygiene.py plan`
- Verbose plan (debug heuristics):
  - `python tools/calendar_hygiene/calendar_hygiene.py plan --verbose`
- Apply selected actions:
  - `python tools/calendar_hygiene/calendar_hygiene.py apply --plan-id YYYY-MM-DD --actions act-xxxx,act-yyyy`
- Apply dry-run (no writes):
  - `python tools/calendar_hygiene/calendar_hygiene.py apply --plan-id YYYY-MM-DD --actions act-xxxx --dry-run`
- Plan output:
  - `memory/plans/calendar_hygiene/YYYY-MM-DD.json`
- Poke hookup (later):
  - Run `plan`, read the JSON, then call `apply` with explicit action IDs.

### Generate a tool spec (on-demand)
- From a complaint string:
  - `python scripts/generate_tool_spec.py "Annoyed by calendar invite spam"`
- From a Notion item ID:
  - `python scripts/generate_tool_spec.py --notion-id <page_id>`
- Optional JSON output:
  - `python scripts/generate_tool_spec.py "Annoyed by calendar invite spam" --format both`

### 5) Google Workspace MCP (`mcp-gsuite-enhanced`)
Repository location: `mcp-gsuite-enhanced/` (from this repo root).

- [ ] Clone if missing:
  - `git clone https://github.com/ajramos/mcp-gsuite-enhanced.git mcp-gsuite-enhanced`
- [ ] Install dependencies (choose one):
  - Option A (uv): `cd mcp-gsuite-enhanced && uv sync`
  - Option B (venv): `cd mcp-gsuite-enhanced && python3 -m venv .venv && .venv/bin/pip install -e .`
- [ ] Place credential files in `mcp-gsuite-enhanced/` (local only):
  - `.gauth.json` (Google OAuth desktop credentials)
  - `.accounts.json` (account list)
  - `.oauth2.<email>.json` (generated by auth script)
- [ ] Run OAuth per account (this opens a browser):
  - `python auth_setup.py your-email@gmail.com`
- [ ] (Optional) If a server supports Codex login, use `codex mcp login <server>`.
- [ ] Add the MCP server (run from this repo root so `$(pwd)` is correct):
  - If using uv:
    - `codex mcp add mcp-gsuite-enhanced -- uv --directory "$(pwd)/mcp-gsuite-enhanced" run mcp-gsuite-enhanced --gauth-file "$(pwd)/mcp-gsuite-enhanced/.gauth.json" --accounts-file "$(pwd)/mcp-gsuite-enhanced/.accounts.json" --credentials-dir "$(pwd)/mcp-gsuite-enhanced"`
  - If using venv:
    - `codex mcp add mcp-gsuite-enhanced -- "$(pwd)/mcp-gsuite-enhanced/.venv/bin/mcp-gsuite-enhanced" --gauth-file "$(pwd)/mcp-gsuite-enhanced/.gauth.json" --accounts-file "$(pwd)/mcp-gsuite-enhanced/.accounts.json" --credentials-dir "$(pwd)/mcp-gsuite-enhanced"`
- [ ] Test:
  - `codex mcp list`
  - `codex exec "List my calendars"`
  - `codex exec "Show my unread emails"`

### 6) Local task analysis scripts (optional)
- [ ] `source venv/bin/activate && python scripts/work_task_analyzer.py`
- [ ] `source venv/bin/activate && python scripts/personal_task_analyzer.py`
- [ ] `source venv/bin/activate && python scripts/personal_project_analyzer.py`

## Notes
- Do not commit secrets. Keep tokens in env vars and auth files in `mcp-gsuite-enhanced/`.
- When credentials or OAuth are required, stop and ask before pasting or running anything.
- Update `CONTEXT.md` whenever IDs, paths, or setup decisions change.
- If a script seems stuck, re-run with `--verbose` to stream Codex output.
- Disable spinners with `--no-progress` if you want plain logs.
