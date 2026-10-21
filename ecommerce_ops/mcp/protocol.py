"""
JSON-RPC 2.0 Protocol Specifications & MCP Message Types.
Follows the Anthropic Model Context Protocol (MCP) schema (specification 2024-11-05).
"""

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


class MCPErrorCode:
    """Standard JSON-RPC 2.0 and MCP Error Codes."""

    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603


@dataclass
class MCPTool:
    """Represents an executable Tool exposed via Model Context Protocol."""

    name: str
    description: str
    input_schema: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


def format_jsonrpc_response(request_id: Any, result: Any) -> str:
    """Format a successful JSON-RPC 2.0 response."""
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": result,
        }
    )


def format_jsonrpc_error(
    request_id: Any, code: int, message: str, data: Optional[Any] = None
) -> str:
    """Format a standard JSON-RPC 2.0 error response."""
    err: Dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": err,
        }
    )
