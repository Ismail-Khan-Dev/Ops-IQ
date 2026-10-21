"""
OpsIQ Model Context Protocol (MCP) Server.

Enables external AI clients (Claude Desktop, Cursor, OpenAI assistants, and enterprise agent swarms)
to natively inspect Shopify stores, execute 3PL warehouse fulfillment holds, evaluate return unit economics,
and calculate real-time margin preservation via Anthropic's Model Context Protocol (MCP).
"""

__version__ = "1.0.0"
__protocol_version__ = "2024-11-05"

from ecommerce_ops.mcp.protocol import MCPTool
from ecommerce_ops.mcp.server import MCPServer
from ecommerce_ops.mcp.tools import TOOLS, execute_tool

__all__ = [
    "MCPServer",
    "MCPTool",
    "TOOLS",
    "execute_tool",
    "__version__",
    "__protocol_version__",
]
