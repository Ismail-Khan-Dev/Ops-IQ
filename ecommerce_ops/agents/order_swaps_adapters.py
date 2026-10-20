"""Input/output adapters for the OrderSwapsAgentLLM."""

from __future__ import annotations

from typing import Any, Dict, Optional


def adapt_input(state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Select the first out-of-stock item that has available swaps."""
    items = state.get("out_of_stock_items", [])
    if not items:
        items = state.get("active_orders", [])
    for item in items:
        if not isinstance(item, dict):
            continue
        swaps = item.get("available_swaps", [])
        if swaps:
            return item
    return None


def adapt_output(llm_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Transform LLM swap result into a decision dict."""
    if not llm_result:
        return None
    from ecommerce_ops.safety.guardrails import GUARDRAIL_VIOLATION_KEY

    if llm_result.get("guardrail_violation"):
        return {
            "action_type": "SWAP_ITEM",
            "reasoning": "Input blocked by safety guardrail; quarantined for HITL.",
            "confidence": 0.0,
            "requires_approval": True,
            "data": {
                GUARDRAIL_VIOLATION_KEY: llm_result[GUARDRAIL_VIOLATION_KEY],
                "risk_score": 1.0,
            },
        }
    if not llm_result.get("should_swap"):
        return None
    confidence = float(llm_result.get("confidence") or 0.5)
    return {
        "action_type": "SWAP_ITEM",
        "reasoning": llm_result.get("reasoning", ""),
        "confidence": confidence,
        "requires_approval": True,
        "data": {
            "original_sku": llm_result.get("original_sku", ""),
            "swap_sku": llm_result.get("swap_sku", ""),
            "swap_name": llm_result.get("swap_name", ""),
            "price_difference": float(llm_result.get("price_difference") or 0),
        },
    }
