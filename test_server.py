#!/usr/bin/env python3
"""
MCP Server Debug Test
===================
This is a minimal test server to debug MCP deployment issues.
It creates a FastMCP server with basic endpoints to verify the integration is working.

Usage:
    python test_server.py
    
Then test with:
    curl -X POST http://localhost:8000/mcp \
      -H "Content-Type: application/json" \
      -H "Accept: application/json, text/event-stream" \
      -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
    curl http://localhost:8000/mcp
    curl http://localhost:8000/
"""

import os
import uvicorn
from fastmcp import FastMCP

def create_test_server():
    """
    Create a minimal MCP server for debugging deployment issues.
    This server includes basic endpoints to verify routing is working.
    """
    
    # Create the MCP server instance
    # This is the main FastMCP object that will handle MCP protocol
    mcp = FastMCP("DebugTestServer")
    
    # Add a test tool to verify MCP functionality
    @mcp.tool
    def debug_test_tool(message: str = "test") -> str:
        """
        A simple test tool to verify MCP is working.
        
        Args:
            message: Test message to echo back
            
        Returns:
            Confirmation message with the input
        """
        return f"MCP Server received: {message}"
    
    # Add a second test tool to verify multiple tools work
    @mcp.tool  
    def server_status() -> dict:
        """
        Returns server status information for debugging.
        
        Returns:
            Dictionary with server status details
        """
        return {
            "status": "running",
            "server_name": "DebugTestServer", 
            "message": "MCP server is functioning correctly"
        }
    
    return mcp

def main():
    """
    Main function to run the test server.
    """
    
    # Print startup information
    print("=" * 50)
    print("MCP Debug Test Server Starting")
    print("=" * 50)
    
    # Create the MCP server
    mcp_server = create_test_server()
    
    # Create the ASGI application in stateless HTTP mode so CI can
    # validate the MCP protocol with a single JSON-RPC request.
    app = mcp_server.http_app(path="/mcp", stateless_http=True)

    port = int(os.getenv("PORT", "8000"))
    
    # Print debug information
    print(f"Server will be available at:")
    print(f"  MCP endpoint: http://localhost:{port}/mcp")
    print()
    print("Test commands:")
    print(
        f'  curl -X POST http://localhost:{port}/mcp '
        '-H "Content-Type: application/json" '
        '-H "Accept: application/json, text/event-stream" '
        '-d \'{"jsonrpc":"2.0","id":1,"method":"tools/list"}\''
    )
    print(f"  curl http://localhost:{port}/mcp")
    print()
    print("If tools/list returns 200, the MCP transport is working correctly.")
    print("=" * 50)
    
    # Start the server
    # Using host="0.0.0.0" makes it accessible from outside the container/VM
    # log_level="debug" provides maximum debugging information
    uvicorn.run(
        app,
        host="0.0.0.0", 
        port=port,
        log_level="debug",
        access_log=True  # Log all requests for debugging
    )

if __name__ == "__main__":
    main()
