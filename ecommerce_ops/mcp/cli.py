"""
CLI Runner for OpsIQ Model Context Protocol (MCP) Server.
Usage:
    python -m ecommerce_ops.mcp.cli --transport stdio
    python -m ecommerce_ops.mcp.cli --list-tools
"""

import argparse
import asyncio
import json
import sys

from ecommerce_ops.mcp.server import MCPServer
from ecommerce_ops.mcp.tools import TOOLS


def main():
    parser = argparse.ArgumentParser(description="OpsIQ Model Context Protocol (MCP) Server")
    parser.add_argument(
        "--transport",
        choices=["stdio"],
        default="stdio",
        help="MCP transport layer (default: stdio for Claude Desktop / Cursor)",
    )
    parser.add_argument(
        "--list-tools",
        action="store_true",
        help="Print all available OpsIQ MCP tools in JSON format and exit",
    )

    args = parser.parse_args()

    if args.list_tools:
        tool_manifest = [t.to_dict() for t in TOOLS]
        print(json.dumps(tool_manifest, indent=2))
        sys.exit(0)

    server = MCPServer()
    if args.transport == "stdio":
        asyncio.run(server.run_stdio())


if __name__ == "__main__":
    main()
