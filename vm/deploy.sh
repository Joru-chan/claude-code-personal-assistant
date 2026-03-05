#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG_FILE="$SCRIPT_DIR/config.sh"

if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "Missing vm/config.sh. Copy vm/config.example.sh first." >&2
  exit 1
fi

# shellcheck source=/dev/null
source "$CONFIG_FILE"

restart_only=0
if [[ "${1:-}" == "--restart-only" || "${1:-}" == "--restart" ]]; then
  restart_only=1
  shift
fi

if [[ "$restart_only" -eq 1 ]]; then
  if [[ -z "${VM_HOST:-}" || -z "${VM_USER:-}" || -z "${VM_SSH_KEY:-}" || -z "${VM_SERVICE:-}" ]]; then
    echo "Missing VM_HOST, VM_USER, VM_SSH_KEY, or VM_SERVICE in vm/config.sh." >&2
    exit 1
  fi
else
  if [[ -z "${VM_HOST:-}" || -z "${VM_USER:-}" || -z "${VM_SSH_KEY:-}" || -z "${VM_DEST_DIR:-}" || -z "${VM_SERVICE:-}" || -z "${VM_LOCAL_SRC:-}" ]]; then
    echo "Missing required VM_* variables in vm/config.sh." >&2
    exit 1
  fi
fi

if [[ "$restart_only" -eq 0 ]]; then
  LOCAL_SRC="$VM_LOCAL_SRC"
  if [[ "$LOCAL_SRC" != /* ]]; then
    LOCAL_SRC="$ROOT_DIR/$LOCAL_SRC"
  fi

  if [[ ! -d "$LOCAL_SRC" ]]; then
    echo "VM_LOCAL_SRC does not exist: $LOCAL_SRC" >&2
    exit 1
  fi
fi

RSYNC_EXCLUDES=(
  "--exclude=venv/"
  "--exclude=__pycache__/"
  "--exclude=*.pyc"
  "--exclude=*.bak*"
  "--exclude=*~"
  "--exclude=.env"
  "--exclude=memory/"
  "--exclude=.git/"
)

if [[ "$restart_only" -eq 0 ]]; then
  echo "Deploying from $LOCAL_SRC to $VM_USER@$VM_HOST:$VM_DEST_DIR"

  rsync -az "${RSYNC_EXCLUDES[@]}" \
    -e "ssh -i $VM_SSH_KEY" \
    "$LOCAL_SRC/" "$VM_USER@$VM_HOST:$VM_DEST_DIR/"

  VENV_PY="${VM_VENV_PY:-/home/ubuntu/mcp-server-template/src/venv/bin/python}"
  REMOTE_REQUIREMENTS="$VM_DEST_DIR/requirements.txt"
  echo "Syncing dependencies (if requirements.txt exists)"
  ssh -i "$VM_SSH_KEY" "$VM_USER@$VM_HOST" \
    "if [ -f '$REMOTE_REQUIREMENTS' ]; then '$VENV_PY' -m pip install -r '$REMOTE_REQUIREMENTS'; else echo 'No requirements.txt found.'; fi"
else
  echo "Restart-only mode: skipping rsync and dependency sync."
fi

echo "Restarting service: $VM_SERVICE"
ssh -i "$VM_SSH_KEY" "$VM_USER@$VM_HOST" \
  "sudo systemctl daemon-reload && sudo systemctl restart $VM_SERVICE"

MCP_URL="${VM_MCP_URL:-https://mcp-lina.duckdns.org/mcp}"
HEALTH_URL="${VM_HEALTH_URL:-https://mcp-lina.duckdns.org/health}"

echo "MCP health check: $MCP_URL"
if command -v curl >/dev/null 2>&1; then
  if "$SCRIPT_DIR/mcp_curl.sh" --list --raw >/tmp/mcp-list-response.log 2>/tmp/mcp-list-error.log; then
    echo "MCP reachable via tools/list."
    echo "MCP response preview:"
    sed -n '1,3p' /tmp/mcp-list-response.log
  else
    echo "WARN: MCP tools/list failed."
    sed -n '1,20p' /tmp/mcp-list-error.log || true
    echo "WARN: MCP health check failed; falling back to HTTP /health."
    if [[ "$HEALTH_URL" == *"/mcp" ]]; then
      echo "WARN: HEALTH_URL ends with /mcp. Prefer /health for HTTP checks."
    fi
    echo "HTTP health check: $HEALTH_URL"
    health_response=$(curl -sS -w "\nHTTP_STATUS:%{http_code}\n" "$HEALTH_URL" || true)
    health_status=$(printf "%s" "$health_response" | tail -n1 | sed "s/HTTP_STATUS://")
    health_first_line=$(printf "%s" "$health_response" | head -n1)
    echo "Health status: ${health_status:-unknown}"
    echo "Health body (first line): ${health_first_line:-<empty>}"
  fi
else
  echo "WARN: curl not found; skipping health check."
fi
