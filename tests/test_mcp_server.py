"""
Unit & Integration Tests for OpsIQ Model Context Protocol (MCP) Server.
Validates JSON-RPC 2.0 handshake, tool discovery, execution handlers, and error codes.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from ecommerce_ops.mcp.protocol import MCPErrorCode
from ecommerce_ops.mcp.server import MCPServer
from ecommerce_ops.mcp.tools import TOOLS, execute_tool


@pytest.fixture
def mcp_server():
    return MCPServer()


# ── 1. Protocol Handshake & Discovery Tests ─────────────────────────────────


@pytest.mark.asyncio
async def test_mcp_initialize(mcp_server):
    req = json.dumps({"jsonrpc": "2.0", "id": "init-1", "method": "initialize"})
    resp_raw = await mcp_server.handle_request(req)
    resp = json.loads(resp_raw)

    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == "init-1"
    assert resp["result"]["protocolVersion"] == "2024-11-05"
    assert resp["result"]["serverInfo"]["name"] == "opsiq-shopify-operations"
    assert "tools" in resp["result"]["capabilities"]


@pytest.mark.asyncio
async def test_mcp_tools_list(mcp_server):
    req = json.dumps({"jsonrpc": "2.0", "id": "list-1", "method": "tools/list"})
    resp_raw = await mcp_server.handle_request(req)
    resp = json.loads(resp_raw)

    assert resp["jsonrpc"] == "2.0"
    tools = resp["result"]["tools"]
    assert len(tools) >= 7

    tool_names = [t["name"] for t in tools]
    assert "opsiq_assess_order_fraud" in tool_names
    assert "opsiq_hold_fulfillment_order" in tool_names
    assert "opsiq_release_fulfillment_order" in tool_names
    assert "opsiq_evaluate_return_economics" in tool_names
    assert "opsiq_recommend_order_swap" in tool_names
    assert "opsiq_get_margin_metrics" in tool_names
    assert "opsiq_verify_store_readiness" in tool_names


@pytest.mark.asyncio
async def test_mcp_ping(mcp_server):
    req = json.dumps({"jsonrpc": "2.0", "id": "ping-1", "method": "ping"})
    resp_raw = await mcp_server.handle_request(req)
    resp = json.loads(resp_raw)

    assert resp["id"] == "ping-1"
    assert resp["result"] == {}


# ── 2. Tool Execution Tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mcp_call_fraud_assessment(mcp_server):
    req = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": "fraud-1",
            "method": "tools/call",
            "params": {
                "name": "opsiq_assess_order_fraud",
                "arguments": {
                    "order_id": "99988",
                    "total_price": 1450.0,
                    "customer_email": "suspicious@tempmail.com",
                },
            },
        }
    )
    resp_raw = await mcp_server.handle_request(req)
    resp = json.loads(resp_raw)

    assert resp["result"]["isError"] is False
    content_text = resp["result"]["content"][0]["text"]
    data = json.loads(content_text)

    assert data["order_id"] == "99988"
    assert data["fraud_risk_score"] > 0
    assert "recommended_action" in data


@pytest.mark.asyncio
async def test_mcp_call_return_economics(mcp_server):
    req = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": "return-1",
            "method": "tools/call",
            "params": {
                "name": "opsiq_evaluate_return_economics",
                "arguments": {
                    "item_price": 32.0,
                    "category": "apparel",
                    "return_reason": "sizing_fit",
                },
            },
        }
    )
    resp_raw = await mcp_server.handle_request(req)
    resp = json.loads(resp_raw)

    assert resp["result"]["isError"] is False
    content_text = resp["result"]["content"][0]["text"]
    data = json.loads(content_text)

    assert data["strategy"] in ("keep_it_credit", "instant_exchange")
    assert data["preserved_margin"] > 0


@pytest.mark.asyncio
async def test_mcp_call_order_swap(mcp_server):
    req = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": "swap-1",
            "method": "tools/call",
            "params": {
                "name": "opsiq_recommend_order_swap",
                "arguments": {
                    "original_price": 75.0,
                    "swap_price": 80.0,
                },
            },
        }
    )
    resp_raw = await mcp_server.handle_request(req)
    resp = json.loads(resp_raw)

    assert resp["result"]["isError"] is False
    content_text = resp["result"]["content"][0]["text"]
    data = json.loads(content_text)

    assert data["preserved_gmv"] == 80.0
    assert data["margin_delta"] > 0


@pytest.mark.asyncio
async def test_mcp_call_hold_fulfillment_order(mcp_server):
    with patch(
        "ecommerce_ops.connectors.shopify.fulfillment_interceptor.FulfillmentHoldInterceptor.intercept_order_for_3pl",
        new_callable=AsyncMock,
    ) as mock_intercept:
        mock_intercept.return_value = {"intercepted": True, "held_fulfillments": [101]}

        req = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": "hold-1",
                "method": "tools/call",
                "params": {
                    "name": "opsiq_hold_fulfillment_order",
                    "arguments": {
                        "order_id": "ord_555",
                        "reason": "high_risk_of_fraud",
                        "notes": "Verified fraudulent IP via Claude Desktop",
                    },
                },
            }
        )
        resp_raw = await mcp_server.handle_request(req)
        resp = json.loads(resp_raw)

        assert resp["result"]["isError"] is False
        data = json.loads(resp["result"]["content"][0]["text"])
        assert data["order_id"] == "ord_555"
        assert data["status"] == "held"
        assert data["warehouse_pick_prevented"] is True


# ── 3. Error Handling Tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mcp_unknown_tool(mcp_server):
    req = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": "err-1",
            "method": "tools/call",
            "params": {"name": "non_existent_tool", "arguments": {}},
        }
    )
    resp_raw = await mcp_server.handle_request(req)
    resp = json.loads(resp_raw)

    assert "error" in resp
    assert resp["error"]["code"] == MCPErrorCode.METHOD_NOT_FOUND
    assert "not registered" in resp["error"]["message"]


@pytest.mark.asyncio
async def test_mcp_invalid_json(mcp_server):
    req = "INVALID_JSON_STRING"
    resp_raw = await mcp_server.handle_request(req)
    resp = json.loads(resp_raw)

    assert "error" in resp
    assert resp["error"]["code"] == MCPErrorCode.PARSE_ERROR
