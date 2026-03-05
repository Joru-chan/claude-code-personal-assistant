#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/config.sh"
CONFIG_EXAMPLE="$SCRIPT_DIR/config.example.sh"

if [[ -f "$CONFIG_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$CONFIG_FILE"
elif [[ -f "$CONFIG_EXAMPLE" ]]; then
  # shellcheck source=/dev/null
  source "$CONFIG_EXAMPLE"
fi

MCP_URL="${VM_MCP_URL:-https://mcp-lina.duckdns.org/mcp}"
resolve_args=()
if [[ -n "${VM_MCP_RESOLVE:-}" ]]; then
  resolve_args=(--resolve "$VM_MCP_RESOLVE")
fi

build_payload() {
  python3 - "$@" <<'PY'
import json
import sys

name = sys.argv[1] if len(sys.argv) > 1 else ""
raw_args = sys.argv[2] if len(sys.argv) > 2 else "{}"

try:
    args = json.loads(raw_args)
except json.JSONDecodeError as exc:
    print(f"Invalid JSON arguments: {exc}. Raw args: {raw_args}", file=sys.stderr)
    sys.exit(2)

payload = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {"name": name, "arguments": args},
}
print(json.dumps(payload))
PY
}

extract_json_from_body() {
  local raw
  raw="$(cat)"
  if [[ -z "$raw" ]]; then
    return 1
  fi
  local data_line
  data_line="$(printf "%s\n" "$raw" | awk '/^data:/{sub(/^data:[[:space:]]*/,""); last=$0} END{if (last) print last}')"
  if [[ -n "$data_line" ]]; then
    printf "%s" "$data_line"
  else
    printf "%s" "$raw"
  fi
}

header_value() {
  local header_name="$1"
  local headers_file="$2"
  awk -v key="$(printf "%s" "$header_name" | tr '[:upper:]' '[:lower:]')" '
    BEGIN { FS=":" }
    {
      name=tolower($1)
      gsub(/\r/,"",name)
      if (name == key) {
        sub(/^[^:]*:[[:space:]]*/, "", $0)
        gsub(/\r/, "", $0)
        print $0
      }
    }
  ' "$headers_file" | tail -n1
}

post_mcp() {
  local payload="$1"
  local session_id="${2:-}"

  RESPONSE_HEADERS_FILE="$(mktemp)"
  RESPONSE_BODY_FILE="$(mktemp)"
  trap 'rm -f "$RESPONSE_HEADERS_FILE" "$RESPONSE_BODY_FILE"' RETURN

  local curl_cmd=(
    curl -sS
    "${resolve_args[@]}"
    -D "$RESPONSE_HEADERS_FILE"
    -o "$RESPONSE_BODY_FILE"
    -H "Content-Type: application/json"
    -H "Accept: application/json, text/event-stream"
    -d "$payload"
  )
  if [[ -n "$session_id" ]]; then
    curl_cmd+=(-H "mcp-session-id: $session_id")
  fi
  curl_cmd+=("$MCP_URL")

  if ! "${curl_cmd[@]}"; then
    echo "Request failed while calling $MCP_URL" >&2
    return 1
  fi

  RESPONSE_BODY="$(cat "$RESPONSE_BODY_FILE")"
  RESPONSE_HEADERS="$(cat "$RESPONSE_HEADERS_FILE")"
  RESPONSE_SESSION_ID="$(header_value "mcp-session-id" "$RESPONSE_HEADERS_FILE" || true)"

  rm -f "$RESPONSE_HEADERS_FILE" "$RESPONSE_BODY_FILE"
  trap - RETURN
}

initialize_session() {
  local init_payload
  init_payload="$(python3 - <<'PY'
import json

payload = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "clientInfo": {"name": "vm-mcp-curl", "version": "1.0.0"},
        "capabilities": {},
    },
}
print(json.dumps(payload))
PY
)"

  post_mcp "$init_payload"
  local sid="$RESPONSE_SESSION_ID"
  if [[ -z "$sid" ]]; then
    echo "Failed to initialize MCP session: no session id returned." >&2
    return 1
  fi

  local notify_payload='{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}'
  post_mcp "$notify_payload" "$sid" >/dev/null 2>&1 || true
  printf "%s" "$sid"
}

raw_mode=0
list_mode=0
use_local=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --raw)
      raw_mode=1
      shift
      ;;
    --list)
      list_mode=1
      shift
      ;;
    --local)
      use_local=1
      shift
      ;;
    *)
      break
      ;;
  esac
done

if [[ "$use_local" -eq 1 && -n "${VM_MCP_LOCAL_URL:-}" ]]; then
  MCP_URL="$VM_MCP_LOCAL_URL"
fi

name="${1:-}"
if [[ "$list_mode" -eq 0 && -z "$name" ]]; then
  echo "Usage: $0 <tool_name> [json_args]" >&2
  echo "Usage: $0 --list [--local] [--raw]" >&2
  echo "Example: $0 call_memory_distiller_daily '{\"event_text\":\"test\"}'" >&2
  exit 1
fi

if [[ "$list_mode" -eq 1 ]]; then
  payload='{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
else
  if [[ $# -ge 2 ]]; then
    payload="$(build_payload "$1" "$2")"
  else
    payload="$(build_payload "$1")"
  fi
fi

post_mcp "$payload"
if printf "%s" "$RESPONSE_BODY" | grep -qi "Missing session ID"; then
  session_id="$(initialize_session)"
  post_mcp "$payload" "$session_id"
fi

if [[ "$raw_mode" -eq 1 ]]; then
  printf "%s\n" "$RESPONSE_BODY"
  exit 0
fi

data_json="$(printf "%s\n" "$RESPONSE_BODY" | extract_json_from_body || true)"
if [[ -z "$data_json" ]]; then
  echo "ERROR: Could not parse JSON from response body." >&2
  printf "%s\n" "$RESPONSE_BODY"
  exit 1
fi

if command -v jq >/dev/null 2>&1; then
  if ! printf "%s\n" "$data_json" | jq .; then
    echo "ERROR: Response is not valid JSON." >&2
    printf "%s\n" "$RESPONSE_BODY"
    exit 1
  fi
else
  printf "%s\n" "$data_json"
fi
