#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/config.sh"

if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "Missing vm/config.sh. Copy vm/config.example.sh first." >&2
  exit 1
fi

# shellcheck source=/dev/null
source "$CONFIG_FILE"

HEALTH_URL="${VM_HEALTH_URL:-https://mcp-lina.duckdns.org/health}"

echo "== HTTP health =="
curl -i "$HEALTH_URL" || true
echo ""
echo "== MCP tools/list =="
./vm/mcp_curl.sh --list
