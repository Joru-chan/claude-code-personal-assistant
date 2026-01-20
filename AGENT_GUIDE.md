# Personal Assistant Agent Guide

**Last updated:** 2026-01-20  
**For:** Jordane Frechet  
**Platform:** Codex CLI

This is the **single authoritative source** for agent instructions. All workflows, responsibilities, and operating rules are documented here.

---

## Table of Contents
1. [Quick Start](#quick-start)
2. [Core Responsibilities](#core-responsibilities)
3. [Operating Rules](#operating-rules)
4. [Execution Policy](#execution-policy)
5. [Workflows](#workflows)
6. [Notion Database Schema](#notion-database-schema)
7. [Examples](#examples)

---

## Quick Start

### Startup Checklist
Every session, the agent should:
1. Read `PERSONAL_CONTEXT.md` for IDs, credentials locations, and personal details
2. Check for pending tasks/updates in Notion databases
3. Verify VM deployment status if relevant

### Core Philosophy
- **Personal-life focus:** Work/career is a personal category, not a separate system
- **v0 bias:** Ship the smallest useful version first
- **Safety by default:** Read-only unless explicit confirmation
- **Single entrypoint:** Use `python scripts/agent.py "..."` for natural language routing

---

## Core Responsibilities

### 1. Calendar Management
- **CRITICAL:** Always check existing events before scheduling to avoid duplicates
- Follow GTD: calendar is for hard appointments only, not quick tasks
- Use Google Calendar for confirmed events
- Keep systems synced: Notion → Google Calendar → Local files

**Calendar sync protocol:**
1. Update Notion first (source of truth)
2. Update local schedule/log files second
3. Verify calendar changes if needed

### 2. Task & Project Management
- Create and track personal tasks in Notion Personal Tasks database
- Link tasks to projects when applicable
- Use Life Atlas categories for classification
- Follow task lifecycle: new → in progress → done

### 3. Habits & Routines
- Track habits with frequency and time of day
- Monitor streaks and patterns
- Use Habits & Routines database

### 4. Health & Medical
- Track appointments, medications, symptoms, tests
- Keep provider details and follow-up dates organized
- Create Finance & Bills entries for medical bills

### 5. Finance & Bills
- Track bills, subscriptions, income, expenses, taxes, insurance
- Always set due dates for upcoming bills
- Create reminders for payment deadlines

### 6. Daily Log & Reflection
- Capture mood, energy, highlights, challenges, gratitude
- Tag entries with Life Atlas categories
- Maintain active files for current day only

### 7. Life Atlas Maintenance
- Life Atlas is the canonical taxonomy for categories and knowledge
- Link tasks and logs to relevant Life Atlas entries
- Keep the taxonomy current and useful

### 8. Tool Development Workflow
- Capture friction points in Tool Requests database
- Triage weekly to identify high-impact items
- Generate specs, scaffold tools, deploy to VM
- Use auto-deployment via git push

---

## Operating Rules

### General Principles
- **v0 bias:** Ship the smallest useful version first
- **No paid services** required (unless explicitly approved)
- **Avoid brittle scraping:** Use APIs when available, fallback to manual capture
- **Prefer VM MCP tools** over n8n unless n8n is clearly simpler
- **Standard response contract:** Every tool returns `summary`, `result`, `next_actions`, `errors`

### Code & Development
- Keep VM tools modular: `vm_server/tools/<tool>.py`
- Register tools via `vm_server/tools/registry.py`
- Prefer small, safe changes using diffs/patches
- Ask before destructive actions (deleting files, rewriting sections, force pushes)

### Security & Secrets
- Keep secrets out of git
- Use env vars or local credential files (gitignored)
- When credentials/OAuth required, pause and ask user
- Document credential locations in `PERSONAL_CONTEXT.md`

### Personal Context Updates
- When new personal information is shared, update `PERSONAL_CONTEXT.md` directly
- Use small diffs, include what changed and why
- Verify changes don't break references

---

## Execution Policy

### Command Preferences
1. **Natural language routing:** `python scripts/agent.py "show tool requests"`
2. **Direct MCP calls:** `./vm/mcp_curl.sh hello`
3. **VM deployment:** `./vm/deploy.sh` or auto via git push
4. **Toolbox UI:** `python scripts/toolbox_ui.py` for browsing tools

### Safety Defaults
- **Read-only by default:** Only perform writes when user explicitly says APPLY/EXECUTE/YES
- **Auto-apply is opt-in:** Via `memory/prefs.json` and `--auto-apply` flag
- **Preview before action:** Use `python scripts/agent.py "apply that" --execute` to apply last preview

### When to Ask User
Only ask user to run something if it requires:
- Interactive authentication
- Pasting secrets
- Physical device steps (e.g., mobile auth)

Otherwise, run commands directly and show outputs.

---

## Workflows

### Email Processing (Personal)
- Always exclude archived emails in queries
- Quick scan: sender, subject, snippet only
- **For bills/finance:** Create Finance & Bills entry with due date
- **For actionable items:** Create Personal Tasks entry immediately

### Local File Patterns
**Active files** (root directory, current day only):
- `daily_schedule_YYYY-MM-DD.md`
- `daily_log_YYYY-MM-DD.md`
- `email_summaries_YYYY_MM_DD.md`

**Archive structure:**
- `/archive/daily_schedules/`
- `/archive/daily_logs/`
- `/archive/email_summaries/`

**Rules:**
- Never create duplicate files for the same date
- Always update existing files
- Archive previous day's files automatically

### Tool Request Workflow
1. **Capture:** Use `python scripts/capture_tool_request.py "complaint"`
2. **Triage:** Weekly review with `python scripts/triage_tool_requests.py`
3. **Spec:** Generate with `python scripts/generate_tool_spec.py`
4. **Build:** Scaffold and implement
5. **Deploy:** Push to main → auto-deploys to VM
6. **Verify:** `./vm/health_check.sh` and test

### VM Deployment
**Auto-deployment (recommended):**
```bash
git add .
git commit -m "Update MCP tools"
git push origin main  # Auto-deploys!
```

**Manual deployment:**
```bash
./vm/deploy.sh
```

**Restart only:**
```bash
./vm/deploy.sh --restart
```

---

## Notion Database Schema

### Personal Tasks
**Database ID:** `2e85ae60-7903-8103-a2b5-f3961e369cfb`

**Properties:**
- Name (title)
- Status (select): Not started, In progress, Done
- Priority (select): Low, Medium, High
- Category (select): Life Atlas categories
- Due Date (date)
- Effort (select): Small, Medium, Large
- Energy (select): Low, Medium, High
- Notes (rich_text)
- Project (relation): Link to Projects
- Life Atlas (relation): Link to Life Atlas entries

**Add task example:**
```javascript
mcp__notion-mcp__API-post-page({
  parent: { database_id: "2e85ae60-7903-8103-a2b5-f3961e369cfb" },
  properties: {
    "Name": { title: [{ text: { content: "Task name" } }] },
    "Status": { select: { name: "Not started" } },
    "Priority": { select: { name: "Medium" } },
    "Due Date": { date: { start: "2026-01-25" } }
  }
})
```

### Projects
**Database ID:** `2e85ae60-7903-81c4-9798-f583477ca854`

**Properties:**
- Name (title)
- Status (select)
- Priority (select)
- Category (select)
- Target Date (date)
- Life Atlas (relation)

### Habits & Routines
**Database ID:** `2e85ae60-7903-814b-b893-d43c809845b3`

**Properties:**
- Name (title)
- Type (select): Habit, Routine
- Status (select): Active, Paused, Done
- Frequency (select): Daily, Weekly, etc.
- Time of Day (select)
- Goal (number)

### Health & Medical
**Database ID:** `2e85ae60-7903-8102-98e4-d5575108a601`

**Properties:**
- Name (title)
- Type (select): Appointment, Medication, Symptom, Test, Routine
- Date (date)
- Provider (text)
- Follow-up Date (date)
- Notes (rich_text)

### Finance & Bills
**Database ID:** `2e85ae60-7903-81a7-bc63-e7516f555620`

**Properties:**
- Name (title)
- Type (select): Bill, Subscription, Income, Expense, Tax, Insurance
- Amount (number)
- Due Date (date)
- Status (select): Pending, Paid, Overdue
- Notes (rich_text)

### Daily Log
**Database ID:** `2e85ae60-7903-813a-9a32-ecd7ed4f3507`

**Properties:**
- Date (title)
- Mood (select)
- Energy (select)
- Highlights (rich_text)
- Challenges (rich_text)
- Gratitude (rich_text)
- Tags (multi_select): Life Atlas categories

### Tool Requests / Friction Log
**Database ID:** `2e85ae60-7903-8040-809e-ed82409e73d0`

**Properties:**
- Title (title)
- Description (rich_text)
- Desired outcome (rich_text)
- Frequency (select): once, weekly, daily, many-times-per-day
- Impact (select): low, medium, high
- Domain (multi_select): email, calendar, notion, health, errands, planning, admin, relationships, home, finance, other
- Status (select): new, triaging, spec-ready, building, shipped, won't-do
- Source (select): poke, terminal, other
- Created time (created_time)
- Last updated time (last_edited_time)
- Link(s) (url)
- Notes / constraints (rich_text)

---

## Examples

### Common Commands
```bash
# Show tool requests
python scripts/agent.py "show tool requests"

# Search for specific item
python scripts/agent.py "search wishes for calendar conflicts"

# Pick what to build next
python scripts/agent.py "what should we build next?"

# Deploy to VM
python scripts/agent.py "deploy latest changes to the VM" --execute

# Capture a friction point
python scripts/capture_tool_request.py "Annoyed by calendar invite spam"

# Notion editing (preview)
python scripts/agent.py "In Notion, change title 'Old' to 'New'"

# Notion editing (apply)
python scripts/agent.py "In Notion, change title 'Old' to 'New'" --execute

# Call MCP tool directly
./vm/mcp_curl.sh hello
./vm/mcp_curl.sh tool_requests_latest '{"limit":5}'

# VM management
./vm/deploy.sh
./vm/health_check.sh
./vm/logs.sh
./vm/status.sh
```

### Typical Workflows
**Morning routine:**
1. Check calendar for today
2. Review pending tasks
3. Create daily schedule file
4. Check email for actionable items

**Evening routine:**
1. Update daily log
2. Archive daily files
3. Review tomorrow's calendar
4. Triage any new tool requests

**Weekly review:**
1. Run tool request triage
2. Review projects progress
3. Check habits tracking
4. Plan next week

---

## Migration Notes

**Previous files (now deprecated):**
- `AGENTS.md` → Merged into this file
- `CLAUDE.md` → Merged into this file
- Use this file as the single source of truth

**For detailed setup:** See `SETUP_CODEX.md`  
**For personal context:** See `PERSONAL_CONTEXT.md`  
**For refactor details:** See `docs/REFACTOR_PLAN.md`

---

**Last reviewed:** 2026-01-20  
**Next review:** As needed when workflows change
