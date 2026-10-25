"""
Async Model Context Protocol (MCP) Server.
Supports Standard I/O (stdio) transport for seamless integration with
Claude Desktop, Cursor IDE, and terminal-based LLM assistants.
"""

import asyncio
import json
import logging
import sys
from typing import Any, Dict

from ecommerce_ops.mcp.protocol import (
    MCPErrorCode,
    format_jsonrpc_error,
    format_jsonrpc_response,
)
from ecommerce_ops.mcp.tools import TOOLS, execute_tool

logger = logging.getLogger("ecommerce_ops.mcp.server")


class MCPServer:
    """Model Context Protocol (MCP) Server for OpsIQ E-Commerce Operations."""

    def __init__(self):
        self.tools = {tool.name: tool for tool in TOOLS}
        self.protocol_version = "2024-11-05"
        self.server_info = {
            "name": "opsiq-shopify-operations",
            "version": "1.0.0",
        }

    async def handle_request(self, raw_message: str) -> str:
        """Parses and executes an incoming JSON-RPC 2.0 MCP request."""
        try:
            req = json.loads(raw_message)
        except Exception:
            return format_jsonrpc_error(None, MCPErrorCode.PARSE_ERROR, "Invalid JSON payload")

        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {})

        # 1. MCP Initialization Handshake
        if method == "initialize":
            return format_jsonrpc_response(
                req_id,
                {
                    "protocolVersion": self.protocol_version,
                    "capabilities": {
                        "tools": {"listChanged": False},
                    },
                    "serverInfo": self.server_info,
                },
            )

        # 2. Client Initialized Notification
        elif method == "notifications/initialized":
            return ""

        # 3. Ping / Keep-Alive
        elif method == "ping":
            return format_jsonrpc_response(req_id, {})

        # 4. Tool Discovery
        elif method == "tools/list":
            return format_jsonrpc_response(
                req_id,
                {
                    "tools": [t.to_dict() for t in self.tools.values()],
                },
            )

        # 5. Tool Execution
        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})

            if tool_name not in self.tools:
                return format_jsonrpc_error(
                    req_id,
                    MCPErrorCode.METHOD_NOT_FOUND,
                    f"Tool '{tool_name}' not registered on OpsIQ MCP server",
                )

            try:
                result_data = await execute_tool(tool_name, arguments)
                return format_jsonrpc_response(
                    req_id,
                    {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(result_data, indent=2),
                            }
                        ],
                        "isError": False,
                    },
                )
            except Exception as e:
                logger.error("Error executing MCP tool %s: %s", tool_name, e)
                return format_jsonrpc_response(
                    req_id,
                    {
                        "content": [
                            {
                                "type": "text",
                                "text": f"OpsIQ MCP Tool Execution Error: {str(e)}",
                            }
                        ],
                        "isError": True,
                    },
                )

        # Unhandled Method
        return format_jsonrpc_error(
            req_id,
            MCPErrorCode.METHOD_NOT_FOUND,
            f"Unhandled MCP method: {method}",
        )

    async def run_stdio(self):
        """Runs the MCP server over standard input/output (stdio) cross-platform."""
        logger.info("OpsIQ MCP Server listening on stdio...")

        while True:
            # sys.stdin.readline in worker thread prevents Windows IOCP handle errors ([WinError 6])
            line = await asyncio.to_thread(sys.stdin.readline)
            if not line:
                break
            raw_msg = line.strip()
            if not raw_msg:
                continue

            response_str = await self.handle_request(raw_msg)
            if response_str:
                sys.stdout.write(response_str + "\n")
                sys.stdout.flush()


def main():
    """Main entrypoint for running the MCP server directly."""
    server = MCPServer()
    asyncio.run(server.run_stdio())


if __name__ == "__main__":
    main()
