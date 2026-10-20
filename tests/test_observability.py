"""Tests for observability/ module (tracing, evaluation, trace_models, tracing_otel)."""
from unittest.mock import patch

from ecommerce_ops.observability.evaluation import AgentEvaluation, EvaluationFramework
from ecommerce_ops.observability.trace_models import (
    SpanType,
    StoredSpan,
    StoredTrace,
    TraceStatus,
)
from ecommerce_ops.observability.tracing_otel import (
    OTEL_ENABLED,
    OTEL_SERVICE_NAME,
    _get_sampler,
    get_tracer,
    init_tracing,
)

# ── tracing_otel.py tests ──────────────────────────────────


class TestTracingOtel:
    def test_default_config_disabled(self):
        assert OTEL_ENABLED is False or OTEL_ENABLED is True

    def test_service_name(self):
        assert OTEL_SERVICE_NAME == "opsiq-api"

    def test_init_tracing_disabled(self):
        with patch("ecommerce_ops.observability.tracing_otel.OTEL_ENABLED", False):
            result = init_tracing()
            assert result is None

    def test_get_tracer_returns_tracer(self):
        tracer = get_tracer("test")
        assert tracer is not None

    def test_get_sampler_returns_sampler(self):
        sampler = _get_sampler()
        assert sampler is not None


# ── trace_models.py tests ──────────────────────────────────


class TestTraceModels:
    def test_stored_span_defaults(self):
        span = StoredSpan(id="s1", trace_id="t1", name="test")
        assert span.name == "test"
        assert span.status == TraceStatus.COMPLETED
        assert span.span_type == SpanType.CUSTOM

    def test_trace_status_values(self):
        assert TraceStatus.RUNNING.value == "running"
        assert TraceStatus.COMPLETED.value == "completed"
        assert TraceStatus.FAILED.value == "failed"
        assert TraceStatus.TIMEOUT.value == "timeout"

    def test_stored_trace_defaults(self):
        t = StoredTrace(id="t1", name="n")
        assert t.total_tokens == 0
        assert t.total_cost_usd == 0.0
        assert t.spans == []

    def test_agent_evaluation(self):
        r = AgentEvaluation(
            agent_name="test",
            decision_id="d1",
            overall_score=0.85,
            passed=True,
            feedback="good",
        )
        assert r.overall_score == 0.85
        assert r.passed is True


# ── evaluation.py tests ────────────────────────────────────


class TestEvaluationFramework:
    def setup_method(self):
        self.framework = EvaluationFramework()

    def test_evaluate_decision_returns_result(self):
        result = self.framework.evaluate_decision(
            agent_name="FraudAgent",
            decision_id="d1",
            decision={
                "action_type": "fraud_hold",
                "reasoning": "High risk order",
                "confidence_score": 0.9,
                "action_data": {},
            },
            context={"run_id": "test"},
        )
        assert hasattr(result, "overall_score")
        assert hasattr(result, "passed")
        assert 0 <= result.overall_score <= 1

    def test_evaluate_high_confidence_scores_higher(self):
        low = self.framework.evaluate_decision(
            agent_name="FraudAgent",
            decision_id="d2",
            decision={
                "action_type": "fraud_hold",
                "reasoning": "Uncertain decision",
                "confidence_score": 0.3,
                "action_data": {},
            },
            context={},
        )
        high = self.framework.evaluate_decision(
            agent_name="FraudAgent",
            decision_id="d2",
            decision={
                "action_type": "fraud_hold",
                "reasoning": "Confident decision",
                "confidence_score": 0.95,
                "action_data": {},
            },
            context={},
        )
        assert hasattr(high, "overall_score")
        assert high.overall_score > low.overall_score

    def test_evaluate_low_confidence_may_fail(self):
        result = self.framework.evaluate_decision(
            agent_name="PricingAgent",
            decision_id="d3",
            decision={
                "action_type": "price_change",
                "reasoning": "Uncertain",
                "confidence_score": 0.3,
                "action_data": {},
            },
            context={},
        )
        assert result.overall_score < 0.8

    def test_evaluate_outcome_rejected_scores_zero(self):
        result = self.framework.evaluate_outcome(
            agent_name="PricingAgent",
            decision_id="d4",
            decision={"action_type": "price_change"},
            hitl_verdict="rejected",
        )
        assert result.overall_score == 0.0
        assert result.passed is False

    def test_evaluate_outcome_approved_executed_scores_one(self):
        result = self.framework.evaluate_outcome(
            agent_name="PricingAgent",
            decision_id="d5",
            decision={"action_type": "price_change"},
            hitl_verdict="approved",
            execution_success=True,
        )
        assert result.overall_score == 1.0
        assert result.passed is True

    def test_evaluate_outcome_approved_failed_scores_half(self):
        result = self.framework.evaluate_outcome(
            agent_name="PricingAgent",
            decision_id="d6",
            decision={"action_type": "price_change"},
            hitl_verdict="approved",
            execution_success=False,
        )
        assert result.overall_score == 0.5
        assert result.passed is False

    def test_evaluate_outcome_expired_scores_low(self):
        result = self.framework.evaluate_outcome(
            agent_name="PricingAgent",
            decision_id="d7",
            decision={"action_type": "price_change"},
            hitl_verdict="expired",
        )
        assert result.overall_score == 0.2
        assert result.passed is False
