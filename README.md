# Personal Assistant (Codex)

This repository configures Codex CLI as a personal assistant with Notion and Google Workspace integrations. The assistant is personal-life focused; work/career is handled as a personal category, not a separate work system.

## Documentation

- **`AGENT_GUIDE.md`** - Single authoritative source for agent instructions, workflows, and responsibilities
- **`PERSONAL_CONTEXT.md`** - Personal details, database IDs, and configuration references
- **`SETUP_CODEX.md`** - Setup checklist for MCP integrations
- **`docs/REFACTOR_PLAN.md`** - Repository refactor plan and progress tracking

## Quick Start
1. Follow `SETUP_CODEX.md`.
2. Open `CLAUDE.md` to adjust workflows; use `profile.md` and `SETUP_CODEX.md` for IDs and integration config.
3. Run Codex with this repo as the working directory.

## One Entrypoint: scripts/agent.py
Use the universal router to translate natural language into actions:
- `python scripts/agent.py "show tool requests"`
- `python scripts/agent.py "search wishes for calendar conflicts"`
- `python scripts/agent.py "what should we build next?"`
- `python scripts/agent.py "In Notion, change title \"Old\" to \"New\""`
- `python scripts/agent.py "In Notion, set status triaging for \"Receipt photo\""`
- `python scripts/agent.py "start a new project from my wishes" --execute`
- `python scripts/agent.py "deploy latest changes to the VM" --execute`

## Notion Editor (safe-by-default)
- Preview updates (no writes):
  - `python scripts/agent.py "In Notion, change title \"Old\" to \"New\""`
- Apply updates (explicit):
  - `python scripts/agent.py "In Notion, change title \"Old\" to \"New\"" --execute`
- Low-level MCP calls:
  - `./vm/mcp_curl.sh notion_search '{"query":"Receipt photo","limit":5}'`
  - `./vm/mcp_curl.sh notion_update_page '{"page_id":"<id>","updates":{"title":"New title"},"dry_run":true}'`

## Toolbox UI (read-only)
Browse and search the registered VM MCP tools locally.
- Build the catalog:
  - `python scripts/tool_catalog.py build`
- Start the UI (runs at `http://127.0.0.1:8765`):
  - `python scripts/toolbox_ui.py`
- Use the “Refresh catalog” button after adding new tools.

## Notion Structure (Personal)
The personal system is centered around the Life Atlas database and an “Assistant HQ” page that contains child databases:
- Personal Tasks
- Projects
- Habits & Routines
- Health & Medical
- Finance & Bills
- Daily Log

## Scripts
- `scripts/agent.py`: Universal router for natural language requests.
- `scripts/triage.py`: Deprecated wrapper; use `scripts/fetch_tool_requests.py`.
- `scripts/personal_task_analyzer.py`: Optional task analysis for the Personal Tasks database.
- `scripts/personal_project_analyzer.py`: Optional analysis for the Projects database.
- `scripts/tool_requests_log.py`: Quick entry helper for the Tool Requests / Friction Log backlog.
- `scripts/work_task_analyzer.py`: Legacy and deprecated (work-focused). Kept for reference only.

## Templates
- `templates/weekly_planning_template.md`: Personal weekly planning template.
- `templates/sprint_planning_template.md`: Legacy work template (kept for reference).

## Security
Do not commit secrets. Tokens and OAuth files are kept in local env vars or ignored files.
Use `.env.example` as the template and keep `.env` local only.
