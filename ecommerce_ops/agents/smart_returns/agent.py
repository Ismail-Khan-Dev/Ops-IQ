"""LLM-Powered Smart Returns Agent.

Predicts return likelihood before shipping and recommends preventive actions.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from ecommerce_ops.agents._base import BaseAgent
from ecommerce_ops.memory.llm_cache import llm_response_cache
from ecommerce_ops.safety.guardrails import guardrail_blocked, guardrail_manager

logger = logging.getLogger("ecommerce_ops.agents.smart_returns_llm")

RETURNS_SYSTEM_PROMPT = """You are an expert return-prediction AI for e-commerce.

Analyze orders to predict return likelihood and recommend preventive actions.

Risk Factors for Returns:
1. Product category (apparel = high return rate, electronics = medium)
2. Customer history (repeat returners vs first-time)
3. Order value (very high value = higher return risk)
4. Size/fit dependent items
5. Gift purchases vs self-purchase
6. Delivery distance (long distance = higher return rate)

Output JSON:
{"return_risk": 0.0-1.0, "risk_level": "low|medium|high",
 "reasoning": "str", "confidence": 0.0-1.0,
 "preventive_actions": ["str"],
 "recommended_insurance": bool}

Rules:
- Be data-driven: use the actual numbers provided
- Low risk: <0.3, Medium: 0.3-0.7, High: >0.7
- Always recommend at least one preventive action for high-risk orders
"""


class SmartReturnsAgentLLM(BaseAgent):
    def __init__(self) -> None:
        super().__init__("smart_returns")

    async def analyze(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        cache_key = f"returns:{order_data.get('order_id', 'unknown')}"
        cached = await llm_response_cache.get(cache_key)
        if cached is not None:
            return cached

        violations = guardrail_manager.check_input(str(order_data))
        if violations:
            return guardrail_blocked(violations)

        system = SystemMessage(content=RETURNS_SYSTEM_PROMPT)
        human = HumanMessage(content=self._build_prompt(order_data))

        try:
            response = await self.llm.ainvoke([system, human])
            from ecommerce_ops.agents.cost_tracker import track_llm_cost

            track_llm_cost(response, agent="smart_returns", model="gemini-2.0-flash")

            parsed = self._parse_response(response)
            if parsed:
                parsed["order_id"] = order_data.get("order_id", "")
                await llm_response_cache.set(cache_key, parsed)
                return parsed
        except Exception as e:
            logger.warning("LLM return prediction failed: %s", e)

        return self._rule_based_fallback(order_data)

    def _build_prompt(self, data: Dict[str, Any]) -> str:
        lines = [
            f"Order ID: {data.get('order_id', '?')}",
            f"Total: ${data.get('order_total', 0):.2f}",
            f"Items: {data.get('item_count', 0)}",
            f"Product categories: {', '.join(data.get('categories', ['unknown']))}",
            f"Customer segment: {data.get('customer_segment', 'unknown')}",
            f"Is repeat customer: {data.get('is_repeat_customer', False)}",
            f"Previous returns: {data.get('previous_returns', 0)}",
            f"Delivery distance: {data.get('delivery_distance', 'unknown')}",
            f"Is gift: {data.get('is_gift', False)}",
        ]
        return "\n".join(lines)

    def _parse_response(self, response: Any) -> Optional[Dict[str, Any]]:
        text = response.content if hasattr(response, "content") else str(response)
        try:
            import json

            start = text.index("{")
            end = text.rindex("}") + 1
            return json.loads(text[start:end])
        except (ValueError, json.JSONDecodeError):
            return {
                "return_risk": 0.5,
                "risk_level": "medium",
                "reasoning": text[:500],
                "confidence": 0.5,
                "preventive_actions": ["manual_review"],
            }

    def _rule_based_fallback(self, data: Dict[str, Any]) -> Dict[str, Any]:
        risk = 0.2
        categories = [c.lower() for c in data.get("categories", [])]
        if any(c in ("apparel", "clothing", "shoes", "fashion") for c in categories):
            risk += 0.3
        if int(data.get("previous_returns", 0)) > 2:
            risk += 0.2
        if float(data.get("order_total", 0)) > 200:
            risk += 0.1
        if not data.get("is_repeat_customer", False):
            risk += 0.05

        risk = min(risk, 1.0)
        level = "low" if risk < 0.3 else "medium" if risk < 0.7 else "high"

        actions = []
        if risk > 0.5:
            actions.append("send_size_guide")
        if risk > 0.7:
            actions.append("require_signature")
            actions.append("offer_return_insurance")

        return {
            "return_risk": round(risk, 2),
            "risk_level": level,
            "reasoning": f"Rule-based: categories={categories}, prev_returns={data.get('previous_returns', 0)}",
            "confidence": 0.6,
            "preventive_actions": actions or ["standard_processing"],
            "recommended_insurance": risk > 0.7,
        }
