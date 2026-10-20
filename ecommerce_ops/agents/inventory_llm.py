"""
LLM-Powered Inventory Management Agent
Uses LLM for demand forecasting, reorder optimization, and stock analysis.
"""

import logging
from typing import Any, Dict

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from ecommerce_ops.agents._base import BaseAgent
from ecommerce_ops.agents.cost_tracker import track_llm_cost
from ecommerce_ops.agents.message_bus import AgentMessage, MessageTopics, message_bus
from ecommerce_ops.memory.llm_cache import llm_response_cache
from ecommerce_ops.safety.guardrails import guardrail_blocked, guardrail_manager

logger = logging.getLogger("ecommerce_ops.agents.inventory_llm")


class InventoryAnalysisOutput(BaseModel):
    """Structured output for inventory analysis."""

    product_id: str = Field(description="Product ID")
    sku: str = Field(description="Product SKU")
    current_stock: int = Field(description="Current stock level")
    recommended_action: str = Field(description="Action: maintain, reorder, clearance, discontinue")
    reorder_quantity: int = Field(description="Recommended reorder quantity")
    confidence: float = Field(description="Confidence from 0.0 to 1.0")
    urgency: str = Field(description="Urgency: low, medium, high, critical")
    reasoning: str = Field(description="Detailed reasoning")
    demand_forecast: Dict[str, Any] = Field(description="Demand forecast data")
    cost_impact: float = Field(description="Estimated cost impact in USD")


INVENTORY_SYSTEM_PROMPT = """You are an expert inventory management AI for an e-commerce platform.

Your role is to analyze inventory levels, forecast demand, and optimize stock levels.

Analysis Factors:
1. Current stock level vs historical sales velocity
2. Lead time from suppliers
3. Seasonal demand patterns
4. Product lifecycle stage
5. Storage costs vs stockout costs
6. Supplier reliability scores
7. Promotional calendar impact
8. Competitive landscape

Decision Framework:
- MAINTAIN: Stock levels are optimal
- REORDER: Need to place purchase order
- CLEARANCE: Overstocked, run promotions
- DISCONTINUE: Product not selling, liquidate

Output Format:
- recommended_action: One of the actions above
- reorder_quantity: Units to order (if reorder recommended)
- sku: The product SKU being analyzed
- confidence: 0.0 to 1.0
- urgency: When action is needed
- demand_forecast: Expected sales for next 30/60/90 days
- cost_impact: Financial impact of recommended action

IMPORTANT:
- Consider minimum order quantities (MOQ)
- Factor in storage capacity constraints
- Account for supplier minimums
- Consider bundling opportunities
- Never recommend actions that would cause stockouts on high-velocity items
"""


class InventoryManagementAgentLLM(BaseAgent):
    """LLM-powered inventory management agent."""

    def __init__(self):
        super().__init__(agent_name="inventory_management")
        self.message_bus = message_bus
        self.message_bus.subscribe_agent("inventory_management", self._handle_message)

    async def _handle_message(self, message: AgentMessage):
        """Handle messages from other agents."""
        if message.topic == MessageTopics.INVENTORY_LOW:
            product_data = message.payload
            result = await self.analyze(product_data)
            if result["urgency"] in ["high", "critical"]:
                await self.message_bus.broadcast(
                    sender="inventory_management",
                    payload=result,
                    message_type="alert",
                    topic=MessageTopics.INVENTORY_REORDER,
                )

    async def analyze(self, product_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze inventory using LLM."""
        context = self._build_context(product_data)

        # Guardrail
        input_check = guardrail_manager.check_input(str(product_data))
        if not input_check.passed:
            logger.warning(
                "Input guardrail blocked for InventoryAgent; quarantining for HITL review: %s",
                input_check.violations,
            )
            return guardrail_blocked(input_check.violations)

        # LLM response cache
        cached = await llm_response_cache.get(context, namespace="inventory_management")
        if cached is not None:
            logger.info("Inventory LLM cache hit")
            return cached

        try:
            messages = [
                SystemMessage(content=INVENTORY_SYSTEM_PROMPT),
                HumanMessage(content=context),
            ]

            response = await self.llm.ainvoke(messages)
            track_llm_cost(response, agent="inventory_management")
            analysis = self._parse_response(response.content, product_data)

            # Validate output
            output_check = guardrail_manager.validate_agent_output(
                analysis,
                required_fields=[
                    "product_id",
                    "sku",
                    "current_stock",
                    "recommended_action",
                    "confidence",
                    "urgency",
                    "reasoning",
                ],
                valid_decisions=["maintain", "reorder", "clearance", "discontinue"],
            )
            if not output_check.passed:
                return self._rule_based_fallback(product_data)

            await llm_response_cache.set(context, analysis, namespace="inventory_management")

            return analysis

        except Exception as e:
            logger.error(f"LLM analysis failed: {e}")
            return self._rule_based_fallback(product_data)

    def _build_context(self, product_data: Dict[str, Any]) -> str:
        """Build analysis context."""
        return f"""
Analyze inventory for this product:

Product ID: {product_data.get("product_id", "unknown")}
Product Name: {product_data.get("name", "unknown")}
Current Stock: {product_data.get("current_stock", 0)} units
Daily Sales (avg): {product_data.get("daily_sales", 0):.1f} units
Lead Time: {product_data.get("lead_time_days", 7)} days
Supplier MOQ: {product_data.get("supplier_moq", 1)} units
Storage Cost/Day: ${product_data.get("storage_cost_per_day", 0.50):.2f}
Unit Cost: ${product_data.get("unit_cost", 0):.2f}
Category: {product_data.get("category", "unknown")}
Last Restock: {product_data.get("last_restock_date", "unknown")}

Provide your inventory analysis with recommended action, reorder quantity, and urgency.
"""

    def _parse_response(self, response: str, product_data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse LLM response."""
        try:
            import json
            import re

            json_match = re.search(r'\{[^{}]*"recommended_action"[^{}]*\}', response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                result["product_id"] = product_data.get("product_id", "unknown")
                result["sku"] = product_data.get("sku", "")
                result["current_stock"] = product_data.get("current_stock", 0)
                return result

            return self._rule_based_fallback(product_data)

        except Exception as e:
            logger.error(f"Failed to parse response: {e}")
            return self._rule_based_fallback(product_data)

    def _rule_based_fallback(self, product_data: Dict[str, Any]) -> Dict[str, Any]:
        """Rule-based fallback."""
        current_stock = product_data.get("current_stock", 0)
        daily_sales = product_data.get("daily_sales", 1)
        lead_time = product_data.get("lead_time_days", 7)

        days_of_stock = current_stock / max(daily_sales, 0.1)
        reorder_point = daily_sales * lead_time * 1.5

        if days_of_stock < lead_time:
            urgency = "critical"
            action = "reorder"
        elif days_of_stock < reorder_point / daily_sales:
            urgency = "high"
            action = "reorder"
        elif days_of_stock > 90:
            urgency = "medium"
            action = "clearance"
        else:
            urgency = "low"
            action = "maintain"

        return {
            "product_id": product_data.get("product_id", "unknown"),
            "current_stock": current_stock,
            "recommended_action": action,
            "reorder_quantity": int(daily_sales * 30),
            "urgency": urgency,
            "reasoning": f"Rule-based: {days_of_stock:.0f} days of stock remaining",
            "demand_forecast": {"30_days": int(daily_sales * 30)},
            "cost_impact": 0,
        }
