"""Centralized LLM cost tracking for all agents.

Gemini 2.0 Flash pricing (as of 2024):
- Input: $0.075 per 1M tokens
- Output: $0.30 per 1M tokens

Usage:
    from ecommerce_ops.agents.cost_tracker import track_llm_cost

    response = await self.llm.ainvoke(messages)
    track_llm_cost(response, agent="fraud", model="gemini-2.0-flash")
"""

import logging

logger = logging.getLogger("ecommerce_ops.cost_tracker")

# Gemini 2.0 Flash pricing per 1M tokens
MODEL_PRICING = {
    "gemini-2.0-flash": {"input": 0.075, "output": 0.30},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
    "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "deepseek-chat": {"input": 0.14, "output": 0.28},
}


def track_llm_cost(response, agent: str, model: str = "gemini-2.0-flash") -> dict:
    """Extract token usage from LangChain response and record cost metrics.

    Returns dict with tokens_input, tokens_output, cost_usd.
    """
    try:
        usage = {}
        if hasattr(response, "response_metadata"):
            usage = response.response_metadata.get("token_usage", {})
        elif hasattr(response, "usage_metadata"):
            usage = response.usage_metadata or {}

        tokens_input = usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0) or 0
        tokens_output = usage.get("completion_tokens", 0) or usage.get("output_tokens", 0) or 0

        if tokens_input == 0 and tokens_output == 0:
            return {"tokens_input": 0, "tokens_output": 0, "cost_usd": 0.0}

        pricing = MODEL_PRICING.get(model, MODEL_PRICING["gemini-2.0-flash"])
        cost_usd = (tokens_input * pricing["input"] + tokens_output * pricing["output"]) / 1_000_000

        try:
            from ecommerce_ops.api.metrics import (
                METRIC_LLM_COST_DOLLARS,
                METRIC_LLM_DAILY_COST,
                METRIC_LLM_TOKENS_INPUT,
                METRIC_LLM_TOKENS_OUTPUT,
            )

            METRIC_LLM_TOKENS_INPUT.labels(agent=agent, model=model).inc(tokens_input)
            METRIC_LLM_TOKENS_OUTPUT.labels(agent=agent, model=model).inc(tokens_output)
            METRIC_LLM_COST_DOLLARS.labels(agent=agent, model=model).inc(cost_usd)
            METRIC_LLM_DAILY_COST.inc(cost_usd)
        except Exception:
            pass

        if cost_usd > 0.01:
            logger.info(
                "LLM cost: agent=%s model=%s in=%d out=%d cost=$%.4f",
                agent,
                model,
                tokens_input,
                tokens_output,
                cost_usd,
            )

        return {
            "tokens_input": tokens_input,
            "tokens_output": tokens_output,
            "cost_usd": round(cost_usd, 6),
        }
    except Exception as e:
        logger.warning("Failed to track LLM cost: %s", e)
        return {"tokens_input": 0, "tokens_output": 0, "cost_usd": 0.0}
