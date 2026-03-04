# Deployment Fix Documentation

## Overview

This document explains the deployment issues that were affecting the MCP server and the solutions implemented to resolve them.

## The Problem

### Original Issue: FastMCP Health Endpoint

The deployment workflow required an HTTP `/health` endpoint to verify the server was running. However, FastMCP's `http_app()` method returns a Starlette application that doesn't easily support adding custom routes or endpoints.

**Multiple attempts were made:**

1. **FastAPI decorators** (`@app.get()`) - Failed with `AttributeError: 'StarletteWithLifespan' object has no attribute 'get'`
2. **Starlette `add_route()`** - Didn't work properly, still returned 404
3. **Starlette `Route` objects** - Still resulted in 404 Not Found
4. **Custom ASGI middleware** - Variable scope issues and complexity

### The "Nuclear Option" Debug Mode

To diagnose the issue, a debug mode was implemented that responded to **all HTTP requests** with a 200 OK response and debug information. This was useful for troubleshooting but had a critical flaw:

**It completely disabled the MCP server functionality.**

The debug stub replaced the entire FastMCP application:

```python
# DEBUG MODE (OLD - BROKEN)
async def respond_to_everything(scope, receive, send):
    # Returns debug info for any request
    response = JSONResponse({"ok": True, "debug": {...}})
    await response(scope, receive, send)

app = respond_to_everything  # ← MCP server disabled!
```

**Impact:**
- ✅ HTTP requests returned 200 OK (deployment appeared successful)
- ✅ Service was running (systemd showed active)
- ❌ **MCP functionality was completely broken**
- ❌ **All tools (Notion, weather, receipts, etc.) were inaccessible**

## The Solution

### 1. Restore Production MCP Server

**File:** `vm_server/server.py`

Reverted from debug mode to the actual production FastMCP server:

```python
# PRODUCTION MODE (NEW - WORKING)
from fastmcp import FastMCP
from tools.registry import register_tools

mcp = FastMCP("Lina Serendipity MCP Server")
app = mcp.http_app(stateless_http=True)
register_tools(mcp)  # ← Tools are now registered and functional
```

**Result:** MCP server is fully operational with all tools working.

### 2. Systemd-Based Health Checks

**File:** `.github/workflows/deploy.yml`

Instead of trying to add a `/health` endpoint to FastMCP, we verify the service through systemd:

```bash
# Check if service is active
sudo systemctl is-active --quiet mcp-server.service

# Verify service details
systemctl show -p ActiveState mcp-server.service
systemctl show -p ExecMainStatus mcp-server.service
```

**Benefits:**
- ✅ No need to modify FastMCP application
- ✅ More reliable than HTTP endpoints
- ✅ Directly checks service health at OS level
- ✅ Detects crashes and restarts

### 3. MCP Protocol Validation

**File:** `.github/workflows/deploy.yml`

Tests actual MCP functionality by sending a JSON-RPC request:

```bash
curl -X POST "$MCP_URL" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'
```

**Validation checks:**
1. HTTP response is 2xx
2. Response is valid JSON-RPC format
3. Response contains `"result"` field (not `"error"`)
4. Tools are listed in the response
5. Tool count is displayed

**Benefits:**
- ✅ Tests actual MCP protocol, not just HTTP connectivity
- ✅ Verifies tools are registered and accessible
- ✅ Ensures server is functionally working
- ✅ Catches configuration errors early

### 4. Comprehensive Verification Steps

The deployment workflow now includes:

1. **Service Status Check** - Systemd active state
2. **Port Verification** - Port 8000 is listening
3. **Process Check** - Python/uvicorn processes running
4. **MCP Protocol Test** - JSON-RPC tools/list request
5. **Service Logs** - Recent logs for troubleshooting

## Deployment Workflow

### Successful Deployment Checklist

When deployment succeeds, all of these are verified:

- ✅ SSH connection established
- ✅ Code synced via rsync
- ✅ Dependencies installed
- ✅ Service restarted
- ✅ Service is active (systemd)
- ✅ Port 8000 is listening
- ✅ MCP protocol responds correctly
- ✅ Tools are registered

### Failure Detection

The workflow will fail if:

- ❌ Service is not active
- ❌ Port 8000 is not listening
- ❌ MCP protocol returns errors
- ❌ No tools are registered
- ❌ Invalid JSON-RPC response

## Troubleshooting

### Service Not Starting

```bash
# Check service status
sudo systemctl status mcp-server.service

# View recent logs
sudo journalctl -u mcp-server.service -n 50

# Check for Python errors
sudo journalctl -u mcp-server.service | grep -i error
```

### Port Not Listening

```bash
# Check if something else is using port 8000
sudo netstat -tlnp | grep 8000
sudo lsof -i :8000

# Check firewall
sudo ufw status
```

### MCP Protocol Failing

```bash
# Test manually
curl -X POST http://localhost:8000 \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'

# Check server logs for errors
sudo journalctl -u mcp-server.service -f
```

### Tools Not Registered

```bash
# Verify tools directory exists
ls -la /path/to/vm_server/tools/

# Check for import errors in logs
sudo journalctl -u mcp-server.service | grep -i "import\|module"

# Verify registry.py is working
python3 -c "from tools.registry import register_tools; print('OK')"
```

## Testing Locally

### Test the MCP Server

```bash
# Start the server
cd vm_server
python3 server.py

# In another terminal, test MCP protocol
curl -X POST http://localhost:8000 \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'
```

### Expected Response

```json
{
  "jsonrpc": "2.0",
  "result": {
    "tools": [
      {"name": "hello", "description": "..."},
      {"name": "get_weather", "description": "..."},
      {"name": "notion_create_page", "description": "..."}
      // ... more tools
    ]
  },
  "id": 1
}
```

## Architecture Decision

### Why Not Add a Health Endpoint?

**Problem:** FastMCP's `http_app()` doesn't support adding custom routes easily.

**Considered Options:**

1. **Modify FastMCP library** - Requires upstream changes, maintenance burden
2. **Complex ASGI middleware** - Error-prone, adds complexity
3. **Separate health server** - Additional port, extra process to manage
4. **Reverse proxy** - Infrastructure complexity

**Chosen Solution:** Systemd + MCP protocol validation

**Why this approach?**
- ✅ No modifications to FastMCP needed
- ✅ Tests actual functionality, not just HTTP
- ✅ Uses standard systemd practices
- ✅ Simple and maintainable
- ✅ More reliable than custom endpoints

## Future Improvements

### Potential Enhancements

1. **Add health check tool** - MCP tool that returns server stats
2. **Monitoring integration** - Send metrics to monitoring system
3. **Automated rollback** - Revert deployment if validation fails
4. **Canary deployments** - Test on one instance before full rollout
5. **Integration tests** - Test actual tool invocations, not just listing

### Upstream Contribution

Consider contributing to FastMCP:
- Add support for custom ASGI middleware
- Provide built-in health check endpoint option
- Document best practices for deployment

## References

- [FastMCP Documentation](https://github.com/jlowin/fastmcp)
- [Systemd Service Management](https://www.freedesktop.org/software/systemd/man/systemctl.html)
- [JSON-RPC 2.0 Specification](https://www.jsonrpc.org/specification)
- [MCP Protocol Specification](https://modelcontextprotocol.io/)

## Summary

**Before this fix:**
- Server in debug mode, MCP disabled
- HTTP endpoints return 200 but server non-functional
- Deployment succeeds but tools inaccessible

**After this fix:**
- Production MCP server running
- Systemd-based health verification
- MCP protocol validation ensures functionality
- All tools registered and accessible
- Reliable deployment verification

The fix solves the original problem without requiring FastMCP modifications and ensures the server is not just running, but actually functional.
