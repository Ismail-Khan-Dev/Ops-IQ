"""Input/output adapters for the DynamicPricingAgentLLM."""

from __future__ import annotations

from typing import Any, Dict, Optional


def adapt_input(state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Select the highest-priority product for pricing analysis.

    Priority: lowest margin first (most room to optimize), then lowest stock.
    """
    items = [
        i
        for i in state.get("inventory_data", [])
        if isinstance(i, dict) and i.get("sku") and float(i.get("price") or 0) > 0
    ]
    if not items:
        return None

    # Sort by margin (lowest first), then by stock (lowest first)
    def margin(item):
        price = float(item.get("price") or 0)
        cost = float(item.get("unit_cost") or item.get("cost") or 0)
        if price <= 0:
            return 0
        return (price - cost) / price

    items.sort(key=lambda i: (margin(i), float(i.get("stock") or 0)))
    item = items[0]

    return {
        "sku": item.get("sku"),
        "current_price": float(item.get("price") or 0),
        "cost": float(item.get("unit_cost") or item.get("cost") or 0),
        "stock": int(item.get("stock") or 0),
        "daily_sales": float(item.get("daily_sales") or 0),
        "competitor_price": item.get("competitor_price"),
        "category": item.get("category"),
        "variant_id": item.get("variant_id"),
    }


def adapt_output(llm_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Transform LLM pricing result into a decision dict."""
    if not llm_result:
        return None
    from ecommerce_ops.safety.guardrails import GUARDRAIL_VIOLATION_KEY

    if llm_result.get("guardrail_violation"):
        return {
            "action_type": "UPDATE_PRICE",
            "reasoning": (
                "Input blocked by safety guardrail (prompt-injection); quarantined "
                "for human review — not auto-executed."
            ),
            "confidence": 0.0,
            "requires_approval": True,
            "data": {
                GUARDRAIL_VIOLATION_KEY: llm_result[GUARDRAIL_VIOLATION_KEY],
                "risk_score": 1.0,
            },
        }

    recommended_price = llm_result.get("recommended_price", 0)
    change_pct = llm_result.get("change_percent", 0)
    confidence = float(llm_result.get("confidence") or 0.5)

    if recommended_price <= 0:
        return None

    return {
        "action_type": "UPDATE_PRICE",
        "reasoning": llm_result.get("reasoning", ""),
        "confidence": confidence,
        "requires_approval": abs(change_pct) > 5 or confidence < 0.9,
        "data": {
            "sku": llm_result.get("sku", ""),
            "old_price": llm_result.get("current_price", 0),
            "new_price": recommended_price,
            "change_percent": round(change_pct, 1),
            "strategy": llm_result.get("strategy", "llm"),
            "demand_signal": llm_result.get("demand_signal", "normal"),
            "urgency": llm_result.get("urgency", "low"),
            "variant_id": llm_result.get("variant_id"),
        },
    }
