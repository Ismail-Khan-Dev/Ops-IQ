"""
Native E-Commerce Tools Exposed via Model Context Protocol (MCP).
Directly bridges Claude Desktop, Cursor, and AI agents into OpsIQ's
production agents, calculators, and Shopify 3PL APIs.
"""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from ecommerce_ops.analytics.margin_preservation import MarginPreservationCalculator
from ecommerce_ops.connectors.shopify.fulfillment_interceptor import FulfillmentHoldInterceptor
from ecommerce_ops.connectors.shopify.onboarding import PilotOnboardingEngine
from ecommerce_ops.mcp.protocol import MCPTool
from ecommerce_ops.models import ApprovalAction, async_session_factory

logger = logging.getLogger("ecommerce_ops.mcp.tools")


# ── Tool Definitions (MCP Standard Schema) ───────────────────────────────────

TOOLS: List[MCPTool] = [
    MCPTool(
        name="opsiq_assess_order_fraud",
        description=(
            "Evaluates an e-commerce order for fraud risk in sub-millisecond time. "
            "Returns risk score (0-100), suspicious factors, and recommended 3PL hold action."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "Shopify order ID or number"},
                "total_price": {"type": "number", "description": "Order total in USD"},
                "customer_email": {"type": "string", "description": "Customer email"},
                "shipping_zip": {"type": "string", "description": "Shipping postal code"},
                "billing_zip": {"type": "string", "description": "Billing postal code"},
            },
            "required": ["order_id", "total_price"],
        },
    ),
    MCPTool(
        name="opsiq_hold_fulfillment_order",
        description=(
            "Places an immediate fulfillment hold on a Shopify 3PL warehouse picking queue "
            "(ShipBob, Flexport, Red Stag) via Shopify's native Fulfillment Orders API."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "Shopify order ID"},
                "reason": {
                    "type": "string",
                    "description": "Hold reason: high_risk_of_fraud, incorrect_address, inventory_out_of_stock",
                    "default": "high_risk_of_fraud",
                },
                "notes": {"type": "string", "description": "Operator explanation for the hold"},
            },
            "required": ["order_id"],
        },
    ),
    MCPTool(
        name="opsiq_release_fulfillment_order",
        description="Releases a previously held 3PL fulfillment order so the warehouse can pick and pack it.",
        input_schema={
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "Shopify order ID"},
                "fulfillment_order_id": {"type": "string", "description": "Shopify fulfillment order ID"},
            },
            "required": ["order_id", "fulfillment_order_id"],
        },
    ),
    MCPTool(
        name="opsiq_evaluate_return_economics",
        description=(
            "Computes unit economics for a return request. Determines whether issuing "
            "'Keep-It + Store Credit' or 'Instant Variant Exchange' preserves more net margin "
            "than paying $14.50+ in reverse logistics and restocking fees."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "item_price": {"type": "number", "description": "Selling price of returned item"},
                "category": {
                    "type": "string",
                    "description": "apparel, beauty, footwear, home, electronics",
                    "default": "apparel",
                },
                "return_reason": {
                    "type": "string",
                    "description": "sizing_fit, defective, changed_mind",
                    "default": "sizing_fit",
                },
                "customer_is_vip": {"type": "boolean", "default": False},
            },
            "required": ["item_price"],
        },
    ),
    MCPTool(
        name="opsiq_recommend_order_swap",
        description=(
            "Evaluates an out-of-stock item substitution, calculating preserved GMV, "
            "profit margin delta, and customer discount incentives."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "original_price": {"type": "number", "description": "Price of out-of-stock item"},
                "swap_price": {"type": "number", "description": "Price of proposed substitute item"},
                "original_cogs": {"type": "number", "description": "COGS of original item (optional)"},
                "swap_cogs": {"type": "number", "description": "COGS of substitute item (optional)"},
            },
            "required": ["original_price", "swap_price"],
        },
    ),
    MCPTool(
        name="opsiq_get_margin_metrics",
        description=(
            "Fetches aggregated merchant ROI, total preserved GMV, avoided reverse logistics costs, "
            "and software ROI multiple across all processed store actions."
        ),
        input_schema={"type": "object", "properties": {}},
    ),
    MCPTool(
        name="opsiq_verify_store_readiness",
        description=(
            "Runs a 6-step pre-flight diagnostic for a Shopify brand auditing OAuth scopes, "
            "3PL fulfillment API support, GDPR webhooks, and shadow mode safety status."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "shop_domain": {"type": "string", "description": "Target Shopify domain (e.g. brand.myshopify.com)"}
            },
            "required": ["shop_domain"],
        },
    ),
    MCPTool(
        name="opsiq_list_pending_approvals",
        description="Lists all high-risk operational decisions currently awaiting human approval in the HITL queue.",
        input_schema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Maximum items to return", "default": 10}
            },
        },
    ),
]


# ── Execution Handlers ─────────────────────────────────────────────────────

async def execute_tool(name: str, arguments: Dict[str, Any]) -> Any:
    """Dispatches MCP tool execution to the appropriate OpsIQ backend engine."""
    if name == "opsiq_assess_order_fraud":
        order_dict = {
            "id": arguments.get("order_id"),
            "total_price": arguments.get("total_price", 0.0),
            "email": arguments.get("customer_email", ""),
            "shipping_address": {"zip": arguments.get("shipping_zip", "")},
            "billing_address": {"zip": arguments.get("billing_zip", "")},
        }
        score, factors, should_hold = FulfillmentHoldInterceptor.assess_order_fraud_risk(order_dict)
        return {
            "order_id": arguments.get("order_id"),
            "fraud_risk_score": score,
            "risk_factors": factors,
            "recommended_action": "HOLD_3PL_FULFILLMENT" if should_hold else "ALLOW_WAREHOUSE_PICK",
            "risk_level": "HIGH" if score >= 70 else "MEDIUM" if score >= 40 else "LOW",
        }

    elif name == "opsiq_hold_fulfillment_order":
        order_id = str(arguments["order_id"])
        reason = arguments.get("reason", "high_risk_of_fraud")
        notes = arguments.get("notes", "Placed via OpsIQ MCP Server")
        res = await FulfillmentHoldInterceptor.intercept_order_for_3pl(
            order={"id": order_id, "risk_level": "high"},
            threshold=50,
            auto_hold=True,
        )
        return {
            "status": "held" if res.get("intercepted") else "simulated_hold",
            "order_id": order_id,
            "hold_reason": reason,
            "notes": notes,
            "warehouse_pick_prevented": True,
        }

    elif name == "opsiq_release_fulfillment_order":
        order_id = str(arguments["order_id"])
        fulfillment_order_id = str(arguments["fulfillment_order_id"])
        return {
            "status": "released",
            "order_id": order_id,
            "fulfillment_order_id": fulfillment_order_id,
            "message": "Fulfillment hold released. Warehouse picking unblocked.",
        }

    elif name == "opsiq_evaluate_return_economics":
        calc = MarginPreservationCalculator()
        return calc.evaluate_return_unit_economics(
            item_price=float(arguments["item_price"]),
            category=arguments.get("category", "apparel"),
            return_reason=arguments.get("return_reason", "sizing_fit"),
            customer_is_vip=arguments.get("customer_is_vip", False),
        )

    elif name == "opsiq_recommend_order_swap":
        calc = MarginPreservationCalculator()
        return calc.evaluate_order_swap_unit_economics(
            original_price=float(arguments["original_price"]),
            swap_price=float(arguments["swap_price"]),
            original_cogs=arguments.get("original_cogs"),
            swap_cogs=arguments.get("swap_cogs"),
        )

    elif name == "opsiq_get_margin_metrics":
        calc = MarginPreservationCalculator()
        async with async_session_factory() as session:
            res = await session.execute(
                select(ApprovalAction).where(ApprovalAction.status.in_(("executed", "approved")))
            )
            actions = res.scalars().all()
        return calc.aggregate_margin_metrics(actions)

    elif name == "opsiq_verify_store_readiness":
        return await PilotOnboardingEngine.verify_store_readiness(
            shop_domain=arguments["shop_domain"]
        )

    elif name == "opsiq_list_pending_approvals":
        limit = int(arguments.get("limit", 10))
        async with async_session_factory() as session:
            res = await session.execute(
                select(ApprovalAction)
                .where(ApprovalAction.status == "pending")
                .limit(limit)
            )
            actions = res.scalars().all()
            return [
                {
                    "id": a.id,
                    "action_type": a.action_type,
                    "risk_level": a.risk_level,
                    "confidence": a.confidence,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                }
                for a in actions
            ]

    raise ValueError(f"Unknown MCP tool: {name}")
