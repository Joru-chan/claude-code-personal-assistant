# Repository Refactor Plan

**Date:** 2026-01-20  
**Goal:** Simplify setup, reduce complexity, align agent instructions with reality

---

## 📊 Current State Analysis

### Strengths ✅
1. **VM deployment** works well (rsync + systemd)
2. **Auto-deployment** now functional (post-push hook)
3. **Single entrypoint** (`scripts/agent.py`) for routing
4. **MCP integration** architecture is sound
5. **Clear separation** between local scripts and VM tools

### Pain Points 🔴

#### 1. **Documentation Sprawl**
- 5 instruction files: `AGENTS.md`, `CLAUDE.md`, `CONTEXT.md`, `SETUP_CODEX.md`, `README.md`
- Overlapping, sometimes contradictory information
- Hard to know which file is authoritative

#### 2. **Script Redundancy**
- `scripts/` has 16 files (~256KB)
- Some deprecated (`triage.py`, `work_task_analyzer.py`)
- `agent.py` is 101KB single file (2,700+ lines)
- Multiple overlapping workflows (triage vs fetch vs capture)

#### 3. **Complex Setup**
- SETUP_CODEX.md is 165 lines
- Requires manual MCP server configuration
- OAuth setup for Google Workspace is fragile
- Multiple auth files in different locations

#### 4. **Legacy Cruft**
- `legacy/vm/` directory (80KB)
- `.bak` files in `vm_server/`
- Deprecated work-focused scripts
- Old sprint planning templates

#### 5. **Unclear Agent Instructions**
- AGENTS.md references workflows that may not exist
- CLAUDE.md is "reference" but treated as primary by some flows
- Notion database schema scattered across files

#### 6. **Development Friction**
- Tool development workflow not streamlined
- No clear path from "friction log" → spec → implementation
- Testing tools requires VM deployment

---

## 🎯 Refactor Goals

### Primary Objectives
1. **Single source of truth** for agent instructions
2. **Reduce setup complexity** (ideally 3-step quickstart)
3. **Consolidate scripts** (merge/remove redundant ones)
4. **Clear development workflow** (friction → spec → build → deploy)
5. **Better testing** (local + VM)

### Non-Goals (Keep As-Is)
- VM infrastructure (working well)
- MCP server architecture (sound design)
- Notion database structure (stable)
- Auto-deployment (just implemented)

---

## 📋 Refactor Plan

### Phase 1: Documentation Consolidation (1-2 hours)

**1.1 Create Single Agent Guide**
- [ ] Merge `AGENTS.md` + `CLAUDE.md` into `AGENT_GUIDE.md`
- [ ] Make it the single authoritative source
- [ ] Structure: Setup → Workflows → Notion Schema → Examples
- [ ] Delete or mark others as "legacy reference"

**1.2 Simplify Setup**
- [ ] Rewrite `SETUP_CODEX.md` as 3-step quickstart
- [ ] Move detailed MCP setup to appendix
- [ ] Create setup verification script: `scripts/verify_setup.py`
- [ ] Document "minimal mode" (no MCP, local only)

**1.3 Consolidate Context**
- [ ] Merge `profile.md` + `CONTEXT.md` into single `PERSONAL_CONTEXT.md`
- [ ] Auto-update from agent interactions
- [ ] Include all database IDs in one place

**Files affected:**
- Create: `AGENT_GUIDE.md`, `PERSONAL_CONTEXT.md`
- Update: `README.md` (point to new files), `SETUP_CODEX.md` (simplify)
- Archive: `AGENTS.md`, `CLAUDE.md`, `profile.md`, `CONTEXT.md` → `docs/archive/`

---

### Phase 2: Script Consolidation (2-3 hours)

**2.1 Refactor agent.py**
- [ ] Split into modules: `agent/router.py`, `agent/handlers.py`, `agent/notion.py`
- [ ] Move to `scripts/agent/` directory
- [ ] Keep `scripts/agent.py` as thin entrypoint (imports from agent/)
- [ ] Target: <500 lines per file

**2.2 Merge Related Scripts**
- [ ] Merge `capture_tool_request.py` + `tool_requests_log.py` → `tool_requests.py`
- [ ] Merge `fetch_tool_requests.py` + `triage_tool_requests.py` → `triage.py` (replace old one)
- [ ] Keep: `personal_task_analyzer.py`, `personal_project_analyzer.py`, `toolbox_ui.py`

**2.3 Remove Deprecated**
- [ ] Delete `work_task_analyzer.py` (legacy, 22KB)
- [ ] Delete old `triage.py` (775 bytes wrapper)
- [ ] Move to `legacy/scripts/`: `llm_decider.py` (if unused)

**2.4 Utilities**
- [ ] Create `scripts/common/` for shared code
- [ ] Move `prefs.py`, `progress.py` to `scripts/common/`
- [ ] Add `scripts/common/notion.py` for Notion helpers

**Target structure:**
```
scripts/
├── agent.py              # Thin entrypoint
├── agent/                # Agent router modules
│   ├── router.py
│   ├── handlers.py
│   └── notion.py
├── common/               # Shared utilities
│   ├── prefs.py
│   ├── progress.py
│   └── notion.py
├── tool_requests.py      # Unified capture/logging
├── triage.py             # Unified fetch/triage
├── personal_task_analyzer.py
├── personal_project_analyzer.py
├── toolbox_ui.py
├── tool_catalog.py
├── tool_request_scoring.py
├── generate_tool_spec.py
└── verify_setup.py       # New: setup checker
```

---

### Phase 3: Setup Simplification (1-2 hours)

**3.1 MCP Setup Helper**
- [ ] Create `scripts/setup_mcp.py`
- [ ] Interactive prompts for Notion token, Google auth
- [ ] Auto-generates `codex mcp add` commands
- [ ] Verifies connectivity

**3.2 Environment Management**
- [ ] Create `.env.template` with all variables documented
- [ ] Script to copy and fill in: `scripts/init_env.py`
- [ ] Check for `.env` before running scripts

**3.3 Docker Option (Optional)**
- [ ] Create `docker-compose.yml` for local development
- [ ] Includes: Python env, MCP servers, local Notion mock
- [ ] One-command setup: `docker-compose up`

---

### Phase 4: Development Workflow (1-2 hours)

**4.1 Tool Development Guide**
- [ ] Create `docs/TOOL_DEVELOPMENT.md`
- [ ] Clear path: friction log → spec → scaffold → test → deploy
- [ ] Examples for common patterns

**4.2 Local Testing**
- [ ] Create `vm_server/local_runner.py` to run MCP locally
- [ ] Test tools without VM deployment
- [ ] Mock webhook endpoints for testing

**4.3 Template Improvements**
- [ ] Create tool scaffold templates in `templates/tools/`
- [ ] Generate from `scripts/generate_tool_spec.py`
- [ ] Include tests by default

---

### Phase 5: Cleanup (1 hour)

**5.1 Remove Cruft**
- [ ] Delete `.bak` files in `vm_server/`
- [ ] Move `legacy/` outside repo or delete
- [ ] Clean up `static/` (check if used)
- [ ] Review `.claude/` hooks (still needed?)

**5.2 Dependency Audit**
- [ ] Review `requirements.txt` for unused packages
- [ ] Split into: `requirements-base.txt`, `requirements-dev.txt`
- [ ] Document why each dependency exists

**5.3 Git Hygiene**
- [ ] Add more patterns to `.gitignore`
- [ ] Document worktree usage in README
- [ ] Clean up stale branches

---

## 🚀 Implementation Order

### Week 1: Foundation
1. **Day 1:** Phase 1 (Documentation) - 2 hours
2. **Day 2:** Phase 2.1-2.2 (Script refactor) - 3 hours
3. **Day 3:** Phase 2.3-2.4 (Cleanup scripts) - 1 hour

### Week 2: Tooling
4. **Day 4:** Phase 3 (Setup simplification) - 2 hours
5. **Day 5:** Phase 4 (Development workflow) - 2 hours
6. **Day 6:** Phase 5 (Cleanup) - 1 hour
7. **Day 7:** Testing & documentation review - 1 hour

**Total effort:** ~12 hours over 2 weeks

---

## 📏 Success Metrics

### Before Refactor
- 5 instruction files
- 16 script files (~256KB)
- 165-line setup guide
- ~7,900 lines of Python
- Setup time: ~2-3 hours

### After Refactor (Target)
- 2 instruction files (AGENT_GUIDE.md + PERSONAL_CONTEXT.md)
- 12 script files + agent/ module (~200KB)
- 50-line quickstart
- ~6,500 lines of Python (cleaner)
- Setup time: ~30 minutes

---

## ⚠️ Risks & Mitigation

### Risk 1: Breaking existing workflows
**Mitigation:** Keep old files in `docs/archive/` during transition

### Risk 2: MCP integration changes
**Mitigation:** Document current working commands before changing

### Risk 3: Agent confusion during refactor
**Mitigation:** Update one file at a time, test immediately

### Risk 4: Loss of institutional knowledge
**Mitigation:** Document "why" decisions in AGENT_GUIDE.md

---

## 🔄 Rollback Plan

Each phase is reversible:
1. Keep original files in `docs/archive/`
2. Git tag before each phase: `refactor-phase-N-start`
3. Document breaking changes in `CHANGELOG.md`
4. Test after each phase, rollback if broken

---

## 📝 Next Actions

**Immediate (today):**
1. Review this plan with user
2. Get approval on scope
3. Create `docs/refactor/` tracking directory

**This week:**
1. Start Phase 1 (documentation consolidation)
2. Create new `AGENT_GUIDE.md`
3. Test with Codex CLI

**Next week:**
1. Continue with script refactoring
2. Setup simplification
3. Final cleanup

---

## 💡 Additional Improvements (Future)

- **CI/CD:** GitHub Actions for auto-deployment
- **Monitoring:** Health check dashboard
- **Logging:** Centralized logging for VM tools
- **Backup:** Notion database backup automation
- **Mobile:** Poke integration (iOS Shortcuts)
- **Voice:** Voice capture for friction logs

---

**Prepared by:** GitHub Copilot CLI  
**Review status:** ⏳ Pending user approval
