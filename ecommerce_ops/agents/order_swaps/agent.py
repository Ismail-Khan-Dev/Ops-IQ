"""LLM-Powered Order Swaps Agent.

Suggests product substitutions when an ordered item is out of stock.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from ecommerce_ops.agents._base import BaseAgent
from ecommerce_ops.memory.llm_cache import llm_response_cache
from ecommerce_ops.safety.guardrails import guardrail_blocked, guardrail_manager

logger = logging.getLogger("ecommerce_ops.agents.order_swaps_llm")

SWAP_SYSTEM_PROMPT = """You are an expert product substitution AI for e-commerce.

When an ordered item is out of stock, find the best substitute the customer would accept.

Criteria:
1. Same category or use case
2. Similar price range (within 20% of original)
3. Equal or better customer ratings
4. Available in stock

Rules:
- Never suggest a swap costing >30% above original
- Never swap across different categories
- If no good swap exists, return should_swap=false
- Always require customer approval for swaps
"""

SWAP_OUTPUT_PROMPT = """Return JSON:
{"should_swap": bool, "swap_sku": "str", "swap_name": "str",
 "confidence": 0.0-1.0, "price_difference": float, "reasoning": "str"}
"""


class OrderSwapsAgentLLM(BaseAgent):
    def __init__(self) -> None:
        super().__init__("order_swaps")

    async def analyze(self, swap_data: Dict[str, Any]) -> Dict[str, Any]:
        cache_key = f"swap:{swap_data.get('original_sku', 'unknown')}"
        cached = await llm_response_cache.get(cache_key)
        if cached is not None:
            return cached

        violations = guardrail_manager.check_input(str(swap_data))
        if violations:
            return guardrail_blocked(violations)

        system = SystemMessage(content=SWAP_SYSTEM_PROMPT)
        human = HumanMessage(content=self._build_prompt(swap_data))

        try:
            response = await self.llm.ainvoke([system, human])
            from ecommerce_ops.agents.cost_tracker import track_llm_cost

            track_llm_cost(response, agent="order_swaps", model="gemini-2.0-flash")

            parsed = self._parse_response(response)
            if parsed:
                parsed["original_sku"] = swap_data.get("original_sku", "")
                await llm_response_cache.set(cache_key, parsed)
                return parsed
        except Exception as e:
            logger.warning("LLM swap analysis failed: %s", e)

        return self._rule_based_fallback(swap_data)

    def _build_prompt(self, data: Dict[str, Any]) -> str:
        lines = [
            f"Out-of-stock: {data.get('original_name', '?')} (SKU: {data.get('original_sku', '?')})",
            f"Price: ${data.get('original_price', 0):.2f}",
            f"Category: {data.get('category', '?')}",
            f"Customer: {data.get('customer_segment', 'all')}",
            "",
            "Available substitutes:",
        ]
        for s in data.get("available_swaps", []):
            lines.append(
                f"  - {s.get('name', '?')} (SKU: {s.get('sku', '?')}, "
                f"${s.get('price', 0):.2f}, stock={s.get('stock', 0)}, "
                f"rating={s.get('rating', 0)})"
            )
        lines.append("")
        lines.append("Recommend the best substitute or explain why none is suitable.")
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
                "should_swap": False,
                "reasoning": text[:500],
                "confidence": 0.5,
            }

    def _rule_based_fallback(self, data: Dict[str, Any]) -> Dict[str, Any]:
        original_price = float(data.get("original_price") or 0)
        original_category = data.get("category", "")
        swaps = data.get("available_swaps", [])

        best = None
        best_score = -1.0
        for s in swaps:
            if s.get("stock", 0) <= 0:
                continue
            if s.get("category", "") != original_category:
                continue
            price = float(s.get("price") or 0)
            if original_price > 0:
                ratio = price / original_price
                if ratio > 1.30 or ratio < 0.70:
                    continue
            rating = float(s.get("rating") or 0)
            score = rating + (1.0 - abs(price - original_price) / max(original_price, 1))
            if score > best_score:
                best_score = score
                best = s

        if best:
            price_diff = float(best.get("price") or 0) - original_price
            return {
                "should_swap": True,
                "swap_sku": best.get("sku", ""),
                "swap_name": best.get("name", ""),
                "confidence": 0.7,
                "price_difference": round(price_diff, 2),
                "reasoning": f"Best available: {best.get('name', '?')} in same category within price range",
            }
        return {
            "should_swap": False,
            "reasoning": "No suitable substitute found in same category/price range",
            "confidence": 0.6,
        }
