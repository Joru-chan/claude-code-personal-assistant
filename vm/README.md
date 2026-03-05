# VM Deployment Toolkit

Use these scripts to deploy the local repo to the Ubuntu VM over SSH and
restart the MCP server service.

## Setup
1) Copy the config file and edit values as needed:
   - `cp vm/config.example.sh vm/config.sh`
2) Ensure the SSH key path is correct and readable.
3) Set `VM_LOCAL_SRC` to the local folder that contains the MCP server code
   you want to deploy (defaults to `vm_server/`).

## Scripts
- `vm/ssh.sh`    : open an SSH session to the VM
- `vm/status.sh` : show systemd status + last 50 logs
- `vm/logs.sh`   : tail service logs (journalctl -f) or `--lines N`
- `vm/deploy.sh` : rsync code to VM + restart service + health check
- `vm/test_hook.sh` : test the post-push hook without actually pushing
- `vm/pull_server_from_vm.sh` : pull the live server code from the VM
- `vm/mcp_curl.sh` : call MCP tools (auto-handles MCP session negotiation)
- `vm/health_check.sh` : canonical health check (HTTP + MCP)

## Workflows

### Auto-deployment (Recommended)
When `vm/config.sh` exists, deployment happens automatically on every push to `main`:
```bash
git add .
git commit -m "Update MCP tools"
git push origin main
# 🚀 Deployment triggers automatically!
```

### Manual deployment
1) Deploy: `./vm/deploy.sh`
2) Check health: `./vm/health_check.sh`
3) Call a tool: `./vm/mcp_curl.sh <tool> '{\"...\": \"...\"}'`
4) Pull server code (if needed): `./vm/pull_server_from_vm.sh`
5) Run Toolbox UI: `python3 scripts/toolbox_ui.py`
6) Restart only: `./vm/deploy.sh --restart-only`

## Git Hook Auto-Deployment

**How it works:**
- A `post-push` git hook triggers deployment after pushing to `main`
- Only runs when `vm/config.sh` exists
- Shows deployment progress in your terminal
- Safe: uses the same `deploy.sh` script as manual deployment

**To disable:**
- Delete or rename `vm/config.sh`
- Hook will skip deployment when config is missing

**To test:**
```bash
# Test the hook without pushing
./vm/test_hook.sh

# Or test with an actual push
echo "# Test" >> README.md
git add README.md
git commit -m "Test auto-deploy"
git push origin main
```

## Deploy behavior
- Uses `rsync` to copy `VM_LOCAL_SRC/` to `VM_DEST_DIR/`.
- Excludes: `venv/`, `__pycache__/`, `*.pyc`, `.env`, `memory/`, `.git`.
- No destructive remote commands (no `rm -rf`, no `--delete`).

## Recommended layout
Keep a dedicated server-only folder for deployment. Default:
- `vm_server/` (contains the MCP server code + requirements for the VM)

Use `vm/pull_server_from_vm.sh` to bootstrap `vm_server/` from the live VM
so it matches `/home/ubuntu/mcp-server-template/src`.

## Pull from VM
Use this to bootstrap or recover the server code from the live VM:
```bash
./vm/pull_server_from_vm.sh
```

## Server environment
The current memory-only server expects these env vars (set on VM, not in git):
- `MEMORY_DISTILLER_WEBHOOK_URL`
- `MEMORY_SIGNAL_WEBHOOK_URL` (optional alias for compatibility)
- `MEMORY_RECALL_WEBHOOK_URL`
- `N8N_WEBHOOK_AUTH_HEADER`
- `N8N_WEBHOOK_AUTH_VALUE`
- `PORT` (default `8000`)

Detailed setup and live runbook:
- `docs/MEMORY_MCP_OPERATIONS.md`

## Health check
- Primary MCP check: `./vm/mcp_curl.sh --list`.
- Secondary HTTP check: `GET /health` if exposed by your reverse proxy.

## Notes
- `vm/config.sh` is local-only and gitignored.
- Recommended health check URL: `https://mcp-lina.duckdns.org/health`.
- The health check URL is read from `VM_HEALTH_URL` (defaults to `/health`).
- Set `VM_HEALTH_URL` in `vm/config.sh` if your deployment uses a different URL.
- Deploy verifies MCP reachability via JSON-RPC on `VM_MCP_URL`.
  If that fails, it falls back to the HTTP `/health` endpoint.
- Deploy retries the MCP health check for a few seconds; initial 502s during restart can be normal.
- Deploy runs a dependency sync if `requirements.txt` exists in `VM_DEST_DIR`
  using `VM_VENV_PY` (defaults to `/home/ubuntu/mcp-server-template/src/venv/bin/python`).
- FastMCP streamable HTTP requires `Accept: application/json, text/event-stream`.

## MCP curl helper
Use the wrapper to hit MCP tools with the correct headers:
```bash
./vm/mcp_curl.sh --list
./vm/mcp_curl.sh --list --local
./vm/mcp_curl.sh call_memory_distiller_daily '{"event_text":"memory test"}'
./vm/mcp_curl.sh call_memory_recall_brief_to_poke '{"query":"books","limit":4}'
```

## Add a new tool module
1) Add a module under `vm_server/tools/`.
2) Register it in `vm_server/tools/registry.py`.
3) Deploy: `./vm/deploy.sh`.
4) Validate with `./vm/mcp_curl.sh --list`.

## Legacy scripts
Deprecated admin scripts live in `legacy/vm/`. They are kept for reference,
but the canonical workflow uses the scripts listed above.
