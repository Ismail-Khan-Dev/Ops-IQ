"""
Shadow-mode A/B testing framework for agent strategies (week 8).

When a store runs in shadow mode, decisions are never executed. This module
compares the production agent decision (variant A) against a configurable
baseline strategy (variant B) and records which one would have scored higher,
plus the divergence between them.

Use cases (without ever touching live traffic):

- Validate a proposed confidence threshold before raising ``AUTO_APPROVE_CONFIDENCE_SCORE``.
- Compare the LLM agent against a conservative rule baseline to justify
  investing in (or retiring) a given agent.
- Track whether the two strategies drift apart over time and alert when they
  diverge (see ``monitoring/alerts.yml``).

Everything is fail-open: an A/B worker failure is logged and never breaks the
pipeline run.
"""

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ecommerce_ops.api.metrics import (
    METRIC_AB_DIVERGENCE,
    METRIC_AB_EXPERIMENTS,
    METRIC_AB_WINNER,
)
from ecommerce_ops.models import ABExperimentRun
from ecommerce_ops.observability.evaluation import (
    AgentEvaluation,
    evaluation_framework,
)

logger = logging.getLogger("ecommerce_ops.observability.ab_testing")


@dataclass(frozen=True)
class ABVariant:
    """A scored A/B variant."""

    variant_id: str
    name: str
    description: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)


DEFAULT_BASELINE_PARAMS: Dict[str, Any] = {
    # Baseline B = "conservative rule baseline": veto actions whose confidence
    # is below this floor, and keep risky action types untouched (hold).
    "min_confidence": 0.75,
    "veto_when_below_confidence": True,
}


def build_baseline_decision(decision: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    """Return the variant-B decision produced by the rule baseline.

    The baseline only ever makes the decision *more* conservative, so any
    divergence it shows vs. the agent is attributable to agent over- or
    under-confidence, not to the baseline fabricating new actions.
    """
    baseline = dict(decision)
    min_conf = float(params.get("min_confidence", DEFAULT_BASELINE_PARAMS["min_confidence"]))
    veto = bool(params.get("veto_when_below_confidence", True))

    confidence = baseline.get("confidence_score", 0.0)
    if veto and confidence < min_conf:
        # Veto → replace the proposed action with an explicit no-op so the
        # evaluation framework scores a "did nothing" decision.
        baseline["action_type"] = "no_op"
        baseline["reasoning"] = "baseline veto: agent confidence below rule threshold"
        baseline["vetoed"] = True
    return baseline


def _decision_to_dict(decision: Any) -> Dict[str, Any]:
    """Normalize a supervisor decision into the dict the evaluator expects."""
    return {
        "action_type": getattr(decision, "action_type", ""),
        "reasoning": getattr(decision, "reasoning", ""),
        "confidence_score": getattr(decision, "confidence_score", 0.0),
        "action_data": getattr(decision, "action_data", {}) or {},
    }


async def run_ab_experiment(
    decision: Any,
    evaluation_a: AgentEvaluation,
    run_id: str,
    session: AsyncSession,
    baseline_params: Optional[Dict[str, Any]] = None,
) -> Optional[ABExperimentRun]:
    """Run one shadow A/B comparison and persist it.

    :param decision: the raw agent decision object (variant A's source).
    :param evaluation_a: the already-computed evaluation of variant A.
    :param run_id: pipeline run id the decision belongs to.
    :param session: caller-owned session (transaction committed by caller).
    :param baseline_params: overrides for the variant-B rule baseline.
    :returns: the persisted row, or ``None`` on any failure (fail-open).
    """
    try:
        params = {**DEFAULT_BASELINE_PARAMS, **(baseline_params or {})}
        decision_a = _decision_to_dict(decision)
        decision_b = build_baseline_decision(decision_a, params)

        # Label by the actual agent name when available (e.g. "PricingAgent"),
        # falling back to the supervisor action type.
        agent = getattr(decision, "agent_id", None) or decision_a.get("action_type", "unknown")

        evaluation_b = evaluation_framework.evaluate_decision(
            agent_name=agent,
            decision_id=str(uuid.uuid4()),
            decision=decision_b,
            context={"run_id": run_id, "variant": "B"},
        )

        score_a = evaluation_a.overall_score
        score_b = evaluation_b.overall_score
        divergence = round(abs(score_a - score_b), 4)
        if score_a > score_b + 1e-9:
            winner = "A"
        elif score_b > score_a + 1e-9:
            winner = "B"
        else:
            winner = "tie"

        METRIC_AB_EXPERIMENTS.labels(agent=agent).inc()
        METRIC_AB_WINNER.labels(variant=winner, agent=agent).inc()
        METRIC_AB_DIVERGENCE.labels(agent=agent).set(divergence)

        row = ABExperimentRun(
            run_id=run_id,
            agent_name=agent,
            action_type=decision_a.get("action_type", ""),
            variant_a_score=round(score_a, 4),
            variant_b_score=round(score_b, 4),
            divergence=divergence,
            winner=winner,
            baseline_params=params,
        )
        session.add(row)
        logger.info(
            "AB shadow %s agent=%s scoreA=%.3f scoreB=%.3f divergence=%.3f winner=%s",
            decision_a.get("action_type", "?"),
            agent,
            score_a,
            score_b,
            divergence,
            winner,
        )
        return row
    except Exception:
        logger.exception("AB experiment failed for run %s — skipping (fail-open)", run_id)
        return None
