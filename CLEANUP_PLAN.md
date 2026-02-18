# Repository Cleanup Plan

## Overview

This cleanup simplifies the repository by removing the Notion integration and natural language agent interface, keeping only the core VM deployment system.

## Changes Made

### ✅ Successfully Removed Components

1. **Main Natural Language Agent**
   - ✅ `scripts/agent.py` - Main agent router (101KB file) - REMOVED
   - ✅ `scripts/agent/__init__.py` - Agent module - REMOVED
   - ✅ `scripts/llm_decider.py` - LLM decision logic - REMOVED
   - ✅ `scripts/personal_task_analyzer.py` - Notion task analysis - REMOVED
   - ✅ `scripts/personal_project_analyzer.py` - Notion project analysis - REMOVED
   - ✅ `scripts/sync_tool_requests.py` - Tool request syncing - REMOVED
   - ✅ `scripts/tool_catalog.py` - Tool catalog builder - REMOVED
   - ✅ `scripts/tool_request_scoring.py` - Tool request scoring - REMOVED
   - ✅ `scripts/tool_requests.py` - Tool request management - REMOVED
   - ✅ `scripts/toolbox_ui.py` - Toolbox web UI - REMOVED
   - ✅ `scripts/verify_setup.py` - Setup verification - REMOVED
   - ✅ `scripts/common/__init__.py` - Common utilities - REMOVED
   - ✅ `scripts/common/progress.py` - Progress utilities - REMOVED

2. **Notion-Specific Documentation**
   - ✅ `AGENT_GUIDE.md` - Agent instructions and workflows (12KB) - REMOVED
   - ✅ `PERSONAL_CONTEXT.md` - Personal Notion database details (9.5KB) - REMOVED
   - ✅ `SETUP_CODEX.md` - MCP setup instructions (9.5KB) - REMOVED
   - ✅ `docs/AGENT_PLAYBOOK.md` - Agent playbook - REMOVED
   - ✅ `docs/PANTRY_ENHANCEMENT_PLAN.md` - Feature planning - REMOVED
   - ✅ `docs/POKE_PANTRY_INTEGRATION.md` - Integration docs - REMOVED
   - ✅ `docs/REFACTOR_PLAN.md` - Refactor planning - REMOVED
   - ✅ `docs/TOOL_DEVELOPMENT.md` - Tool development guide - REMOVED

3. **Test and Build Files**
   - ✅ `test_one_item.json` - Test data - REMOVED
   - ✅ `test_receipt.json` - Test receipt data - REMOVED
   - ✅ `Makefile` - Build automation (for agent system) - REMOVED
   - ✅ `requirements.txt` - Python dependencies for agent - REMOVED

4. **New Documentation**
   - ✅ `README.md` - Updated and simplified for VM deployment
   - ✅ `CLEANUP_PLAN.md` - This file documenting the cleanup

### ⚠️ Directories Requiring Manual Cleanup

The following directories still contain files that should be removed manually or in a follow-up:

1. **`.claude/`** - Claude-specific configuration (agents, commands, hooks)
2. **`docs/archive/`** - Archived documentation  
3. **`legacy/`** - Legacy code directory
4. **`scripts/common/prefs.py`** - Preferences file (if it exists)
5. **`static/`** - Static assets for web UI
6. **`templates/`** - Template files (HTML, MD) for agent/UI
7. **`tests/`** - Test files directory
8. **`tools/`** - Tool integrations directory (e.g., calendar_hygiene)
9. **`utils/`** - Utility modules directory

These can be removed with:
```bash
git rm -r .claude docs/archive legacy scripts/common static templates tests tools utils
git commit -m "Complete cleanup: remove remaining agent-related directories"
```

### ✅ Kept Components

1. **VM Deployment System** (Complete and Intact)
   - `vm/` directory with all deployment scripts
   - `vm/README.md` - VM deployment documentation
   - `vm/deploy.sh` - Main deployment script
   - All VM management scripts (ssh.sh, status.sh, logs.sh, health_check.sh, etc.)
   - `vm_server/` - VM server components directory

2. **Repository Basics**
   - `README.md` - Updated and simplified
   - `LICENSE` - Repository license
   - `.gitignore` - Git ignore rules

## Rationale

The cleanup focuses the repository on its core purpose: VM deployment and management. By removing the Notion integration and complex agent system, we:

- Reduce repository complexity
- Remove personal/private context from the codebase
- Create a more maintainable and focused project
- Keep deployment infrastructure intact

## Next Steps

After this cleanup is merged:

1. **Manual cleanup of remaining directories** (listed above)

2. Consider creating separate repositories for:
   - Notion integration tools (if still needed)
   - Personal assistant agent (if desired to continue development)

3. Archive removed components if needed for future reference

4. Update any external documentation or links pointing to removed components

## Rollback Plan

If needed, all removed code is preserved in git history and can be restored by:
```bash
git checkout <previous-commit> -- <file-or-directory>
```

Original state is at commit: `395dfab12036d9cce6298461280c1dfab818ec00`

## Summary

This PR successfully removes the core Notion integration and agent files while preserving the VM deployment system. Some directories with multiple files remain and should be cleaned up manually as a follow-up task.
