"""
Evaluation Metrics and Scoring Framework
Comprehensive evaluation of agent performance and decision quality.
"""

import logging
from datetime import datetime
from enum import StrEnum
from typing import Any, ClassVar, Dict, List, Optional

from pydantic import BaseModel, Field

from ecommerce_ops.utils import utc_now

logger = logging.getLogger("ecommerce_ops.observability.evaluation")


class MetricType(StrEnum):
    """Types of evaluation metrics."""

    BINARY = "binary"  # 0 or 1
    SCALE = "scale"  # 1-5
    CONTINUOUS = "continuous"  # 0.0-1.0
    CATEGORICAL = "categorical"  # predefined categories


class EvaluationDimension(StrEnum):
    """Evaluation dimensions for agent decisions."""

    ACCURACY = "accuracy"
    COMPLETENESS = "completeness"
    TIMELINESS = "timeliness"
    SAFETY = "safety"
    COST_EFFICIENCY = "cost_efficiency"
    USER_SATISFACTION = "user_satisfaction"
    HALLUCINATION = "hallucination"
    REASONING_QUALITY = "reasoning_quality"


class MetricDefinition(BaseModel):
    """Definition of an evaluation metric."""

    name: str
    dimension: EvaluationDimension
    metric_type: MetricType
    description: str
    min_value: float = 0.0
    max_value: float = 1.0
    weight: float = 1.0
    is_required: bool = False


class EvaluationResult(BaseModel):
    """Result of a single metric evaluation."""

    metric_name: str
    dimension: EvaluationDimension
    value: float
    confidence: float = 1.0
    reasoning: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AgentEvaluation(BaseModel):
    """Complete evaluation of an agent decision."""

    agent_name: str
    decision_id: str
    trace_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=utc_now)
    metrics: List[EvaluationResult] = Field(default_factory=list)
    overall_score: float = 0.0
    passed: bool = False
    feedback: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def dimension_scores(self) -> Dict[str, float]:
        """Get scores grouped by dimension."""
        scores = {}
        for metric in self.metrics:
            dim = metric.dimension.value
            if dim not in scores:
                scores[dim] = []
            scores[dim].append(metric.value)
        return {k: sum(v) / len(v) for k, v in scores.items()}

    @property
    def score_breakdown(self) -> Dict[str, Any]:
        """Get detailed score breakdown."""
        return {
            "overall": self.overall_score,
            "passed": self.passed,
            "dimensions": self.dimension_scores,
            "metrics": [
                {
                    "name": m.metric_name,
                    "dimension": m.dimension.value,
                    "value": m.value,
                    "confidence": m.confidence,
                }
                for m in self.metrics
            ],
        }


class EvaluationFramework:
    """Framework for evaluating agent decisions."""

    # Default metric definitions
    DEFAULT_METRICS: ClassVar[Dict[EvaluationDimension, MetricDefinition]] = {
        EvaluationDimension.ACCURACY: MetricDefinition(
            name="decision_accuracy",
            dimension=EvaluationDimension.ACCURACY,
            metric_type=MetricType.BINARY,
            description="Is the decision factually correct?",
            weight=1.0,
        ),
        EvaluationDimension.COMPLETENESS: MetricDefinition(
            name="response_completeness",
            dimension=EvaluationDimension.COMPLETENESS,
            metric_type=MetricType.SCALE,
            description="How complete is the response/decision?",
            max_value=5.0,
            weight=0.8,
        ),
        EvaluationDimension.TIMELINESS: MetricDefinition(
            name="response_time",
            dimension=EvaluationDimension.TIMELINESS,
            metric_type=MetricType.CONTINUOUS,
            description="Was the response timely?",
            weight=0.6,
        ),
        EvaluationDimension.SAFETY: MetricDefinition(
            name="safety_score",
            dimension=EvaluationDimension.SAFETY,
            metric_type=MetricType.BINARY,
            description="Is the decision safe and compliant?",
            weight=1.2,
        ),
        EvaluationDimension.COST_EFFICIENCY: MetricDefinition(
            name="cost_efficiency",
            dimension=EvaluationDimension.COST_EFFICIENCY,
            metric_type=MetricType.CONTINUOUS,
            description="How cost-efficient is the decision?",
            weight=0.7,
        ),
        EvaluationDimension.REASONING_QUALITY: MetricDefinition(
            name="reasoning_quality",
            dimension=EvaluationDimension.REASONING_QUALITY,
            metric_type=MetricType.SCALE,
            description="Quality of reasoning behind the decision",
            max_value=5.0,
            weight=0.9,
        ),
    }

    def __init__(self, threshold: float = 0.7):
        self.threshold = threshold
        self._metrics = dict(self.DEFAULT_METRICS)

    def add_metric(self, metric: MetricDefinition):
        """Add a custom metric."""
        self._metrics[metric.dimension] = metric

    def evaluate_decision(
        self,
        agent_name: str,
        decision_id: str,
        decision: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None,
    ) -> AgentEvaluation:
        """Evaluate a single agent decision."""
        metrics = []

        # Evaluate accuracy
        accuracy = self._evaluate_accuracy(decision, context)
        metrics.append(
            EvaluationResult(
                metric_name="decision_accuracy",
                dimension=EvaluationDimension.ACCURACY,
                value=accuracy,
                confidence=0.9,
                reasoning="Based on decision validation rules",
            )
        )

        # Evaluate completeness
        completeness = self._evaluate_completeness(decision, context)
        metrics.append(
            EvaluationResult(
                metric_name="response_completeness",
                dimension=EvaluationDimension.COMPLETENESS,
                value=completeness,
                confidence=0.85,
                reasoning="Based on required fields coverage",
            )
        )

        # Evaluate safety
        safety = self._evaluate_safety(decision, context)
        metrics.append(
            EvaluationResult(
                metric_name="safety_score",
                dimension=EvaluationDimension.SAFETY,
                value=safety,
                confidence=0.95,
                reasoning="Based on safety rule compliance",
            )
        )

        # Evaluate reasoning quality
        reasoning_quality = self._evaluate_reasoning(decision, context)
        metrics.append(
            EvaluationResult(
                metric_name="reasoning_quality",
                dimension=EvaluationDimension.REASONING_QUALITY,
                value=reasoning_quality,
                confidence=0.8,
                reasoning="Based on reasoning completeness and logic",
            )
        )

        # Evaluate cost efficiency
        cost_efficiency = self._evaluate_cost_efficiency(decision, context)
        metrics.append(
            EvaluationResult(
                metric_name="cost_efficiency",
                dimension=EvaluationDimension.COST_EFFICIENCY,
                value=cost_efficiency,
                confidence=0.85,
                reasoning="Based on financial impact vs benefit",
            )
        )

        # Calculate overall score
        overall_score = self._calculate_overall_score(metrics)

        return AgentEvaluation(
            agent_name=agent_name,
            decision_id=decision_id,
            trace_id=trace_id,
            metrics=metrics,
            overall_score=overall_score,
            passed=overall_score >= self.threshold,
            feedback=self._generate_feedback(metrics, overall_score),
        )

    def evaluate_outcome(
        self,
        agent_name: str,
        decision_id: str,
        decision: Dict[str, Any],
        hitl_verdict: str,
        execution_success: Optional[bool] = None,
        trace_id: Optional[str] = None,
    ) -> AgentEvaluation:
        """Evaluate a decision against the actual HITL outcome (M8).

        This replaces the self-reported vanity metrics with ground-truth
        scores derived from the operator's verdict and execution results:

        - "approved" + executed  -> 1.0 (correct, corroborated)
        - "approved" + failed    -> 0.5 (operator agreed, execution failed)
        - "rejected"             -> 0.0 (operator disagreed with the agent)
        - "expired"              -> 0.2 (no operator decision, action lapsed)
        """
        if hitl_verdict == "rejected":
            overall = 0.0
            passed = False
            feedback = "Operator rejected the decision — agent outcome did not match ground truth"
        elif hitl_verdict == "expired":
            overall = 0.2
            passed = False
            feedback = "Decision expired without operator action"
        elif hitl_verdict == "approved" and execution_success is False:
            overall = 0.5
            passed = False
            feedback = "Operator approved but execution failed"
        elif hitl_verdict in ("approved", "shadow", "auto-approved"):
            overall = 1.0
            passed = True
            feedback = "Decision corroborated by operator (or shadow auto-approval)"
        else:
            overall = 0.0
            passed = False
            feedback = "Unknown outcome"

        metrics = [
            EvaluationResult(
                metric_name="hitl_outcome_accuracy",
                dimension=EvaluationDimension.ACCURACY,
                value=overall,
                confidence=1.0,
                reasoning=f"Ground-truth HITL verdict: {hitl_verdict}",
            ),
            EvaluationResult(
                metric_name="outcome_safety",
                dimension=EvaluationDimension.SAFETY,
                value=1.0 if overall >= 0.5 else 0.0,
                confidence=1.0,
                reasoning="Outcome score below threshold implies unsafe/incorrect agent behavior",
            ),
        ]

        return AgentEvaluation(
            agent_name=agent_name,
            decision_id=decision_id,
            trace_id=trace_id,
            metrics=metrics,
            overall_score=overall,
            passed=passed,
            feedback=feedback,
            metadata={"hitl_verdict": hitl_verdict, "execution_success": execution_success},
        )

    def evaluate_batch(
        self,
        evaluations: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Evaluate a batch of decisions and provide aggregate metrics."""
        results = []
        for item in evaluations:
            result = self.evaluate_decision(
                agent_name=item["agent_name"],
                decision_id=item["decision_id"],
                decision=item["dimension"],
                context=item.get("context"),
                trace_id=item.get("trace_id"),
            )
            results.append(result)

        # Aggregate metrics
        total = len(results)
        passed = sum(1 for r in results if r.passed)
        avg_score = sum(r.overall_score for r in results) / total if total > 0 else 0

        # Dimension averages
        dimension_averages = {}
        for dim in EvaluationDimension:
            dim_scores = [
                r.dimension_scores.get(dim.value, 0)
                for r in results
                if dim.value in r.dimension_scores
            ]
            if dim_scores:
                dimension_averages[dim.value] = sum(dim_scores) / len(dim_scores)

        return {
            "total_evaluated": total,
            "passed": passed,
            "pass_rate": passed / total if total > 0 else 0,
            "average_score": round(avg_score, 3),
            "dimension_averages": dimension_averages,
            "results": [r.score_breakdown for r in results],
        }

    def _evaluate_accuracy(
        self,
        decision: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> float:
        """Evaluate decision accuracy."""
        # Check if decision has required fields
        required_fields = ["action_type", "reasoning", "confidence_score"]
        present = sum(1 for f in required_fields if f in decision)
        field_score = present / len(required_fields)

        # Check confidence level
        confidence = decision.get("confidence_score", 0)
        confidence_score = min(confidence * 1.2, 1.0)  # Boost slightly

        return (field_score + confidence_score) / 2

    def _evaluate_completeness(
        self,
        decision: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> float:
        """Evaluate response completeness (1-5 scale)."""
        score = 1

        if decision.get("reasoning"):
            score += 1
        if decision.get("action_data"):
            score += 1
        if decision.get("impact"):
            score += 1
        if context and len(context) > 0:
            score += 1

        return min(score, 5.0)

    def _evaluate_safety(
        self,
        decision: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> float:
        """Evaluate decision safety."""
        # Check for risky actions
        risky_actions = ["delete", "cancel", "refund", "hold"]
        action_type = decision.get("action_type", "").lower()

        for risky in risky_actions:
            if risky in action_type:
                return 0.5  # Lower safety for risky actions

        # Check confidence threshold
        confidence = decision.get("confidence_score", 0)
        if confidence < 0.5:
            return 0.6

        return 1.0

    def _evaluate_reasoning(
        self,
        decision: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> float:
        """Evaluate reasoning quality (1-5 scale)."""
        reasoning = decision.get("reasoning", "")

        if not reasoning:
            return 1.0

        score = 2  # Base score for having reasoning

        # Length-based scoring
        if len(reasoning) > 100:
            score += 1
        if len(reasoning) > 200:
            score += 1

        # Check for data references
        if any(char.isdigit() for char in reasoning):
            score += 0.5

        return min(score, 5.0)

    def _evaluate_cost_efficiency(
        self,
        decision: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> float:
        """Evaluate cost efficiency."""
        # Check financial impact
        impact = decision.get("impact", {})
        financial_impact = impact.get("financial_impact", 0)

        if financial_impact <= 0:
            return 1.0  # No cost or revenue generating
        elif financial_impact < 100:
            return 0.9
        elif financial_impact < 500:
            return 0.8
        elif financial_impact < 1000:
            return 0.7
        else:
            return 0.6

    def _calculate_overall_score(self, metrics: List[EvaluationResult]) -> float:
        """Calculate weighted overall score."""
        if not metrics:
            return 0.0

        total_weight = 0
        weighted_sum = 0

        for metric in metrics:
            metric_def = self._metrics.get(metric.dimension)
            weight = metric_def.weight if metric_def else 1.0
            normalized_value = metric.value / (metric_def.max_value if metric_def else 1.0)

            weighted_sum += normalized_value * weight * metric.confidence
            total_weight += weight

        return weighted_sum / total_weight if total_weight > 0 else 0.0

    def _generate_feedback(
        self,
        metrics: List[EvaluationResult],
        overall_score: float,
    ) -> str:
        """Generate human-readable feedback."""
        if overall_score >= 0.9:
            return "Excellent decision quality. Meets all evaluation criteria."
        elif overall_score >= 0.7:
            return "Good decision. Meets most criteria with minor improvements possible."
        elif overall_score >= 0.5:
            return "Acceptable decision. Some areas need improvement."
        else:
            return "Decision needs significant improvement. Review reasoning and safety."


# Singleton
evaluation_framework = EvaluationFramework()
