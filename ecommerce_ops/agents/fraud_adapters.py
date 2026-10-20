"""Input/output adapters for the FraudDetectionAgentLLM.

Standalone functions that transform state <-> LLM agent format.
Extracted from AgentFactory for dynamic registry compatibility.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


def adapt_input(state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Select the single highest-value active order for fraud analysis."""
    orders = state.get("active_orders", [])
    if not orders:
        return None
    order = max(orders, key=lambda o: float(o.get("order_total") or 0))
    if not isinstance(order, dict):
        return None
    line_items = order.get("line_items") or []
    return {
        "id": order.get("id", ""),
        "customer_email": order.get("customer_email", ""),
        "total": float(order.get("order_total") or 0),
        "item_count": len(line_items),
        "line_items": line_items,
    }


def adapt_output(llm_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Transform LLM fraud result into a decision dict."""
    if not llm_result:
        return None
    from ecommerce_ops.safety.guardrails import GUARDRAIL_VIOLATION_KEY

    if llm_result.get("guardrail_violation"):
        return {
            "action_type": "HOLD_ORDER",
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
    if llm_result.get("decision") == "approve":
        return None
    return {
        "action_type": "HOLD_ORDER",
        "reasoning": llm_result.get("reasoning", ""),
        "confidence": llm_result.get("confidence", 0.5),
        "requires_approval": llm_result.get("confidence", 0.5) < 0.9,
        "data": {
            "risk_score": llm_result.get("risk_score", 0.5),
            "risk_factors": llm_result.get("risk_factors", []),
            "recommended_actions": llm_result.get("recommended_actions", []),
        },
    }
