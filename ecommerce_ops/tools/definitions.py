"""
Tool Definitions - LangChain Tools with JSON Schemas
Production-grade tool system for all agents.
"""

import logging
from typing import Any, Callable, Dict, List, Optional, Type

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

logger = logging.getLogger("ecommerce_ops.tools.definitions")


# ── Input Schemas ──────────────────────────────────────────


class SendEmailInput(BaseModel):
    """Input for sending an email."""

    to: str = Field(description="Recipient email address")
    subject: str = Field(description="Email subject line")
    body: str = Field(description="Email body content (HTML supported)")
    from_name: str = Field(default="OpsIQ", description="Sender name")
    priority: str = Field(default="normal", description="Priority: low, normal, high, urgent")


class SendSMSInput(BaseModel):
    """Input for sending an SMS."""

    to: str = Field(description="Recipient phone number (E.164 format)")
    message: str = Field(description="SMS message content (max 1600 chars)")
    priority: str = Field(default="normal", description="Priority: low, normal, high")


class UpdateShopifyPriceInput(BaseModel):
    """Input for updating Shopify product price."""

    product_id: str = Field(description="Shopify product ID")
    new_price: float = Field(description="New price in USD")
    compare_at_price: Optional[float] = Field(
        default=None, description="Compare at price (strikethrough)"
    )
    reason: str = Field(description="Reason for price change")


class CreateDiscountCodeInput(BaseModel):
    """Input for creating a Shopify discount code."""

    code: str = Field(description="Discount code (e.g., SAVE10)")
    discount_type: str = Field(description="Type: percentage, fixed_amount, free_shipping")
    value: float = Field(description="Discount value (e.g., 10 for 10%)")
    usage_limit: int = Field(default=1, description="Max number of uses")
    expires_at: Optional[str] = Field(default=None, description="Expiration date (ISO format)")
    min_order_amount: Optional[float] = Field(default=None, description="Minimum order amount")


class CreateShopifyOrderInput(BaseModel):
    """Input for creating a Shopify order."""

    customer_email: str = Field(description="Customer email")
    line_items: List[Dict[str, Any]] = Field(
        description="List of line items [{product_id, quantity, price}]"
    )
    shipping_address: Optional[Dict[str, str]] = Field(default=None, description="Shipping address")
    notes: Optional[str] = Field(default=None, description="Order notes")


class SendSlackMessageInput(BaseModel):
    """Input for sending a Slack message."""

    channel: str = Field(description="Slack channel name or ID")
    message: str = Field(description="Message content")
    thread_ts: Optional[str] = Field(default=None, description="Thread timestamp for replies")


class CreatePurchaseOrderInput(BaseModel):
    """Input for creating a purchase order."""

    supplier_id: str = Field(description="Supplier ID")
    product_id: str = Field(description="Product ID")
    quantity: int = Field(description="Quantity to order")
    unit_cost: float = Field(description="Cost per unit")
    urgency: str = Field(default="normal", description="Urgency: low, normal, high, critical")


class SearchProductsInput(BaseModel):
    """Input for searching Shopify products."""

    query: str = Field(description="Search query")
    limit: int = Field(default=10, description="Max results")
    status: str = Field(default="active", description="Product status: active, draft, archived")


class GetOrderInput(BaseModel):
    """Input for getting order details."""

    order_id: str = Field(description="Shopify order ID")
    include_line_items: bool = Field(default=True, description="Include line items")


class AnalyzeCustomerInput(BaseModel):
    """Input for analyzing customer data."""

    customer_id: str = Field(description="Customer ID")
    include_orders: bool = Field(default=True, description="Include order history")
    include_behavior: bool = Field(default=True, description="Include behavioral data")


class UpdateInventoryInput(BaseModel):
    """Input for updating inventory."""

    product_id: str = Field(description="Product ID")
    quantity: int = Field(description="New quantity")
    location: str = Field(default="main", description="Warehouse location")
    reason: str = Field(description="Reason for update")


class LogAuditEventInput(BaseModel):
    """Input for logging an audit event."""

    event_type: str = Field(description="Event type: auth, data_access, config_change, security")
    action: str = Field(description="Action performed")
    resource: str = Field(description="Resource affected")
    resource_id: Optional[str] = Field(default=None, description="Resource ID")
    success: bool = Field(default=True, description="Whether action succeeded")
    details: Optional[Dict[str, Any]] = Field(default=None, description="Additional details")


class CheckInventoryLevelInput(BaseModel):
    """Input for checking inventory levels."""

    product_id: str = Field(description="Product ID")
    location: Optional[str] = Field(default=None, description="Specific location (or all)")


class GetCustomerHistoryInput(BaseModel):
    """Input for getting customer history."""

    customer_id: str = Field(description="Customer ID")
    days: int = Field(default=90, description="Number of days to look back")
    include_communications: bool = Field(default=True, description="Include email/SMS history")


# ── Tool Functions ──────────────────────────────────────────


async def _send_email(
    to: str, subject: str, body: str, from_name: str = "OpsIQ", priority: str = "normal"
) -> Dict[str, Any]:
    """Send an email via SMTP/SendGrid."""
    logger.info(f"Sending email to {to}: {subject}")
    # In production, integrate with SendGrid/SES
    return {
        "success": True,
        "message_id": f"email_{hash(to + subject)}",
        "to": to,
        "subject": subject,
    }


async def _send_sms(to: str, message: str, priority: str = "normal") -> Dict[str, Any]:
    """Send SMS via Twilio."""
    logger.info(f"Sending SMS to {to}: {message[:50]}...")
    # In production, integrate with Twilio
    return {"success": True, "message_id": f"sms_{hash(to)}", "to": to}


async def _update_shopify_price(
    product_id: str, new_price: float, compare_at_price: Optional[float] = None, reason: str = ""
) -> Dict[str, Any]:
    """Update product price on Shopify."""
    logger.info(f"Updating price for product {product_id} to ${new_price}")
    # In production, use Shopify API
    return {
        "success": True,
        "product_id": product_id,
        "new_price": new_price,
        "compare_at_price": compare_at_price,
    }


async def _create_discount_code(
    code: str,
    discount_type: str,
    value: float,
    usage_limit: int = 1,
    expires_at: Optional[str] = None,
    min_order_amount: Optional[float] = None,
) -> Dict[str, Any]:
    """Create a discount code on Shopify."""
    logger.info(f"Creating discount code: {code} ({discount_type}: {value})")
    # In production, use Shopify API
    return {
        "success": True,
        "code": code,
        "type": discount_type,
        "value": value,
        "usage_limit": usage_limit,
    }


async def _create_shopify_order(
    customer_email: str,
    line_items: List[Dict[str, Any]],
    shipping_address: Optional[Dict[str, str]] = None,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a draft order on Shopify."""
    logger.info(f"Creating order for {customer_email} with {len(line_items)} items")
    # In production, use Shopify API
    return {
        "success": True,
        "order_id": f"order_{hash(customer_email)}",
        "total": sum(item.get("price", 0) * item.get("quantity", 1) for item in line_items),
    }


async def _send_slack_message(
    channel: str, message: str, thread_ts: Optional[str] = None
) -> Dict[str, Any]:
    """Send a Slack message."""
    logger.info(f"Sending Slack message to #{channel}: {message[:50]}...")
    # In production, use Slack API
    return {"success": True, "channel": channel, "ts": f"slack_{hash(message)}"}


async def _create_purchase_order(
    supplier_id: str, product_id: str, quantity: int, unit_cost: float, urgency: str = "normal"
) -> Dict[str, Any]:
    """Create a purchase order."""
    logger.info(f"Creating PO for {quantity} units of {product_id} from supplier {supplier_id}")
    # In production, integrate with procurement system
    return {
        "success": True,
        "po_id": f"po_{hash(supplier_id + product_id)}",
        "total_cost": quantity * unit_cost,
    }


async def _search_products(query: str, limit: int = 10, status: str = "active") -> Dict[str, Any]:
    """Search Shopify products."""
    logger.info(f"Searching products: {query}")
    # In production, use Shopify API
    return {"products": [], "total": 0, "query": query}


async def _get_order(order_id: str, include_line_items: bool = True) -> Dict[str, Any]:
    """Get order details from Shopify."""
    logger.info(f"Getting order {order_id}")
    # In production, use Shopify API
    return {"order_id": order_id, "status": "unknown", "total": 0}


async def _analyze_customer(
    customer_id: str, include_orders: bool = True, include_behavior: bool = True
) -> Dict[str, Any]:
    """Analyze customer data."""
    logger.info(f"Analyzing customer {customer_id}")
    # In production, aggregate from multiple sources
    return {"customer_id": customer_id, "lifetime_value": 0, "segment": "unknown"}


async def _update_inventory(
    product_id: str, quantity: int, location: str = "main", reason: str = ""
) -> Dict[str, Any]:
    """Update inventory level."""
    logger.info(f"Updating inventory for {product_id}: {quantity} units at {location}")
    # In production, use inventory management system
    return {"success": True, "product_id": product_id, "new_quantity": quantity}


async def _log_audit_event(
    event_type: str,
    action: str,
    resource: str,
    resource_id: Optional[str] = None,
    success: bool = True,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Log an audit event."""
    logger.info(f"AUDIT: {event_type} - {action} on {resource} (success={success})")
    # In production, write to audit log database
    return {"success": True, "event_type": event_type, "action": action}


async def _check_inventory_level(product_id: str, location: Optional[str] = None) -> Dict[str, Any]:
    """Check inventory levels."""
    logger.info(f"Checking inventory for {product_id}")
    # In production, query inventory system
    return {"product_id": product_id, "quantity": 0, "location": location or "all"}


async def _get_customer_history(
    customer_id: str, days: int = 90, include_communications: bool = True
) -> Dict[str, Any]:
    """Get customer history."""
    logger.info(f"Getting {days}-day history for customer {customer_id}")
    # In production, query customer database
    return {"customer_id": customer_id, "orders": [], "communications": []}


# ── Tool Registry ──────────────────────────────────────────


class ToolRegistry:
    """Central registry for all tools with permission matrix."""

    def __init__(self):
        self._tools: Dict[str, StructuredTool] = {}
        self._permissions: Dict[str, List[str]] = {}
        self._build_tools()
        self._build_permissions()

    def _build_tools(self):
        """Build all LangChain StructuredTools."""
        tool_defs = [
            ("send_email", _send_email, SendEmailInput, "Send an email to a recipient"),
            ("send_sms", _send_sms, SendSMSInput, "Send an SMS message"),
            (
                "update_shopify_price",
                _update_shopify_price,
                UpdateShopifyPriceInput,
                "Update product price on Shopify",
            ),
            (
                "create_discount_code",
                _create_discount_code,
                CreateDiscountCodeInput,
                "Create a discount code on Shopify",
            ),
            (
                "create_shopify_order",
                _create_shopify_order,
                CreateShopifyOrderInput,
                "Create a draft order on Shopify",
            ),
            (
                "send_slack_message",
                _send_slack_message,
                SendSlackMessageInput,
                "Send a Slack message",
            ),
            (
                "create_purchase_order",
                _create_purchase_order,
                CreatePurchaseOrderInput,
                "Create a purchase order",
            ),
            ("search_products", _search_products, SearchProductsInput, "Search Shopify products"),
            ("get_order", _get_order, GetOrderInput, "Get order details from Shopify"),
            (
                "analyze_customer",
                _analyze_customer,
                AnalyzeCustomerInput,
                "Analyze customer data and segments",
            ),
            ("update_inventory", _update_inventory, UpdateInventoryInput, "Update inventory level"),
            ("log_audit_event", _log_audit_event, LogAuditEventInput, "Log an audit event"),
            (
                "check_inventory_level",
                _check_inventory_level,
                CheckInventoryLevelInput,
                "Check inventory levels",
            ),
            (
                "get_customer_history",
                _get_customer_history,
                GetCustomerHistoryInput,
                "Get customer order history",
            ),
        ]

        for name, func, schema, description in tool_defs:
            self._tools[name] = StructuredTool(
                name=name,
                description=description,
                func=func,
                args_schema=schema,
            )

    def _build_permissions(self):
        """Define which agents can use which tools."""
        self._permissions = {
            "fraud_detection": [
                "get_order",
                "get_customer_history",
                "analyze_customer",
                "send_slack_message",
                "log_audit_event",
            ],
            "inventory_management": [
                "check_inventory_level",
                "update_inventory",
                "search_products",
                "create_purchase_order",
                "send_slack_message",
                "log_audit_event",
            ],
            "price_optimization": [
                "search_products",
                "update_shopify_price",
                "analyze_customer",
                "send_slack_message",
                "log_audit_event",
            ],
            "review_moderation": [
                "get_order",
                "analyze_customer",
                "send_email",
                "send_slack_message",
                "log_audit_event",
            ],
            "marketing_automation": [
                "send_email",
                "send_sms",
                "search_products",
                "analyze_customer",
                "create_discount_code",
                "send_slack_message",
                "log_audit_event",
            ],
            "cart_recovery": [
                "get_customer_history",
                "send_email",
                "send_sms",
                "create_discount_code",
                "analyze_customer",
                "send_slack_message",
                "log_audit_event",
            ],
            "customer_support": [
                "get_order",
                "get_customer_history",
                "analyze_customer",
                "send_email",
                "send_sms",
                "update_inventory",
                "send_slack_message",
                "log_audit_event",
            ],
            "all": list(self._tools.keys()),
        }

    def get_tools_for_agent(self, agent_id: str) -> List[StructuredTool]:
        """Get tools an agent is allowed to use."""
        allowed = self._permissions.get(agent_id, [])
        return [self._tools[name] for name in allowed if name in self._tools]

    def get_all_tools(self) -> List[StructuredTool]:
        """Get all registered tools."""
        return list(self._tools.values())

    def get_tool(self, name: str) -> Optional[StructuredTool]:
        """Get a specific tool by name."""
        return self._tools.get(name)

    def has_permission(self, agent_id: str, tool_name: str) -> bool:
        """Check if agent has permission to use a tool."""
        allowed = self._permissions.get(agent_id, [])
        return tool_name in allowed

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Get JSON schemas for all tools (for OpenAI function calling)."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.args_schema.model_json_schema() if tool.args_schema else {},
                },
            }
            for tool in self._tools.values()
        ]

    def register_tool(
        self,
        name: str,
        func: Callable,
        schema: Type[BaseModel],
        description: str,
        agents: Optional[List[str]] = None,
    ):
        """Register a new tool dynamically."""
        self._tools[name] = StructuredTool(
            name=name,
            description=description,
            func=func,
            args_schema=schema,
        )
        if agents:
            for agent_id in agents:
                if agent_id not in self._permissions:
                    self._permissions[agent_id] = []
                self._permissions[agent_id].append(name)


# Singleton
tool_registry = ToolRegistry()
