"""Input/output adapters for the SmartReturnsAgentLLM."""

from __future__ import annotations

from typing import Any, Dict, Optional


def adapt_input(state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Select the highest-risk pending order for return prediction."""
    orders = state.get("pending_orders", [])
    if not orders:
        orders = state.get("active_orders", [])
    for order in orders:
        if not isinstance(order, dict):
            continue
        if order.get("order_id"):
            return order
    return None


def adapt_output(llm_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Transform LLM return prediction into a decision dict."""
    if not llm_result:
        return None
    from ecommerce_ops.safety.guardrails import GUARDRAIL_VIOLATION_KEY

    if llm_result.get("guardrail_violation"):
        return {
            "action_type": "FLAG_RETURN_RISK",
            "reasoning": "Input blocked by safety guardrail; quarantined for HITL.",
            "confidence": 0.0,
            "requires_approval": True,
            "data": {
                GUARDRAIL_VIOLATION_KEY: llm_result[GUARDRAIL_VIOLATION_KEY],
                "risk_score": 1.0,
            },
        }

    risk = float(llm_result.get("return_risk") or 0)
    if risk < 0.3:
        return None

    confidence = float(llm_result.get("confidence") or 0.5)
    return {
        "action_type": "FLAG_RETURN_RISK",
        "reasoning": llm_result.get("reasoning", ""),
        "confidence": confidence,
        "requires_approval": risk > 0.5,
        "data": {
            "order_id": llm_result.get("order_id", ""),
            "return_risk": risk,
            "risk_level": llm_result.get("risk_level", "medium"),
            "preventive_actions": llm_result.get("preventive_actions", []),
            "recommended_insurance": llm_result.get("recommended_insurance", False),
        },
    }
