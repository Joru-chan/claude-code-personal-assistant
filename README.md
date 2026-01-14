# Personal Assistant (Codex)

This repository configures Codex CLI as a personal assistant with Notion and Google Workspace integrations. The assistant is personal-life focused; work/career is handled as a personal category, not a separate work system.

## How Codex Uses This Repo
- `AGENTS.md` is the primary instruction file Codex follows.
- `CLAUDE.md` is a workflow reference document.
- `SETUP_CODEX.md` is the setup checklist for MCP integrations.
- `profile.md` stores personal context and preferences.
- `CONTEXT.md` stores key IDs and setup decisions for clean-slate recovery.

## Quick Start
1. Follow `SETUP_CODEX.md`.
2. Open `CLAUDE.md` to adjust workflows and database IDs if needed.
3. Run Codex with this repo as the working directory.

## Notion Structure (Personal)
The personal system is centered around the Life Atlas database and an “Assistant HQ” page that contains child databases:
- Personal Tasks
- Projects
- Habits & Routines
- Health & Medical
- Finance & Bills
- Daily Log

## Scripts
- `scripts/personal_task_analyzer.py`: Optional task analysis for the Personal Tasks database.
- `scripts/personal_project_analyzer.py`: Optional analysis for the Projects database.
- `scripts/work_task_analyzer.py`: Legacy and deprecated (work-focused). Kept for reference only.

## Templates
- `templates/weekly_planning_template.md`: Personal weekly planning template.
- `templates/sprint_planning_template.md`: Legacy work template (kept for reference).

## Security
Do not commit secrets. Tokens and OAuth files are kept in local env vars or ignored files.
Use `.env.example` as the template and keep `.env` local only.
