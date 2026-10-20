"""Input/output adapters for the MarketingAutomationAgentLLM."""

from __future__ import annotations

from typing import Any, Dict, Optional


def adapt_input(state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Build marketing context from low-stock inventory items."""
    items = state.get("inventory_data", [])
    if not items:
        return None
    low_stock = [i for i in items if 0 < i.get("stock", 0) < 20]
    if not low_stock:
        return None
    return {
        "trigger": "low_stock",
        "customer": {"segment": "all"},
        "cart_value": 0,
    }


def adapt_output(llm_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Transform LLM marketing result into a decision dict."""
    if not llm_result:
        return None
    from ecommerce_ops.safety.guardrails import GUARDRAIL_VIOLATION_KEY

    if llm_result.get("guardrail_violation"):
        return {
            "action_type": "DRAFT_MARKETING_CAMPAIGN",
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
    confidence = float(llm_result.get("confidence") or 0)
    return {
        "action_type": "DRAFT_MARKETING_CAMPAIGN",
        "reasoning": llm_result.get("reasoning", ""),
        "confidence": confidence,
        "requires_approval": confidence < 0.95 or True,
        "data": {
            "campaign_name": llm_result.get("campaign_name", ""),
            "campaign_type": llm_result.get("campaign_type", "email"),
            "target_audience": llm_result.get("target_audience", {}),
            "content": llm_result.get("content", {}),
            "estimated_reach": llm_result.get("estimated_reach", 0),
            "estimated_ctr": llm_result.get("estimated_ctr", 0),
            "estimated_revenue": llm_result.get("estimated_revenue", 0),
        },
    }
