"""Input/output adapters for the InventoryManagementAgentLLM."""

from __future__ import annotations

from typing import Any, Dict, Optional


def adapt_input(state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Map inventory state to a single product dict for the LLM agent."""
    items = [
        i
        for i in state.get("inventory_data", [])
        if isinstance(i, dict) and i.get("sku")
    ]
    if not items:
        return None
    item = min(items, key=lambda i: float(i.get("stock") or 0))
    stock = item.get("stock")
    if stock is None:
        stock = item.get("current_stock")
    return {
        "product_id": str(
            item.get("variant_id") or item.get("product_id") or item.get("sku")
        ),
        "sku": item.get("sku"),
        "name": item.get("name") or item.get("sku"),
        "current_stock": int(stock or 0),
        "price": float(item.get("price") or 0),
        "unit_cost": float(item.get("unit_cost") or item.get("price") or 0),
        "daily_sales": float(item.get("daily_sales") or 0),
    }


def adapt_output(llm_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Adapt inventory LLM result into a decision dict."""
    if not llm_result:
        return None
    from ecommerce_ops.safety.guardrails import GUARDRAIL_VIOLATION_KEY

    if llm_result.get("guardrail_violation"):
        return {
            "action_type": "DRAFT_PO",
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
    if llm_result.get("recommended_action") != "reorder":
        return None
    sku = llm_result.get("sku")
    reorder_quantity = llm_result.get("reorder_quantity")
    if not sku or not reorder_quantity or reorder_quantity <= 0:
        return None
    confidence = float(llm_result.get("confidence") or 0)
    return {
        "action_type": "DRAFT_PO",
        "reasoning": llm_result.get("reasoning") or "",
        "confidence": confidence,
        "requires_approval": confidence < 0.9,
        "data": {
            "sku": sku,
            "quantity_to_order": int(reorder_quantity),
            "product_id": llm_result.get("product_id") or "",
            "urgency": llm_result.get("urgency") or "medium",
            "demand_forecast": llm_result.get("demand_forecast") or {},
            "cost_impact": float(llm_result.get("cost_impact") or 0),
        },
    }
