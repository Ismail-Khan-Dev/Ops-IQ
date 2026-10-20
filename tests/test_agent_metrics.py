"""Tests for per-agent MetricsCollector (week 12 instrumentation)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ecommerce_ops.observability.agent_metrics import (
    AgentExecutionRecord,
    MetricsCollector,
    SLOResult,
    agent_metrics,
)


class TestAgentExecutionRecord:
    def test_to_dict(self):
        r = AgentExecutionRecord(
            agent="fraud",
            started_at=1.0,
            finished_at=2.0,
            latency_ms=1000.0,
            success=True,
            fallback_used=False,
            tokens_input=100,
            tokens_output=50,
            cost_usd=0.001,
            decision_type="HOLD_ORDER",
            confidence=0.92,
        )
        d = r.to_dict()
        assert d["agent"] == "fraud"
        assert d["latency_ms"] == 1000.0
        assert d["success"] is True
        assert d["fallback_used"] is False
        assert d["tokens_input"] == 100
        assert d["tokens_output"] == 50
        assert d["cost_usd"] == 0.001
        assert d["decision_type"] == "HOLD_ORDER"
        assert d["confidence"] == 0.92
        assert "wall_time" in d

    def test_to_dict_defaults(self):
        r = AgentExecutionRecord(
            agent="inventory",
            started_at=0.0,
            finished_at=1.0,
            latency_ms=500.0,
            success=False,
            fallback_used=True,
            error="timeout",
        )
        d = r.to_dict()
        assert d["tokens_input"] == 0
        assert d["cost_usd"] == 0.0
        assert d["decision_type"] is None
        assert d["error"] == "timeout"


class TestSLOResult:
    def test_all_ok_true(self):
        r = SLOResult(
            agent="fraud",
            p95_latency_ms=3000.0,
            slo_p95_latency_ms=5000.0,
            p95_ok=True,
            success_rate=0.98,
            slo_min_success_rate=0.95,
            success_rate_ok=True,
            sample_count=100,
        )
        assert r.all_ok is True

    def test_all_ok_false_p95_violation(self):
        r = SLOResult(
            agent="fraud",
            p95_latency_ms=7000.0,
            slo_p95_latency_ms=5000.0,
            p95_ok=False,
            success_rate=0.98,
            slo_min_success_rate=0.95,
            success_rate_ok=True,
            sample_count=100,
        )
        assert r.all_ok is False

    def test_all_ok_false_success_rate_violation(self):
        r = SLOResult(
            agent="fraud",
            p95_latency_ms=3000.0,
            slo_p95_latency_ms=5000.0,
            p95_ok=True,
            success_rate=0.80,
            slo_min_success_rate=0.95,
            success_rate_ok=False,
            sample_count=100,
        )
        assert r.all_ok is False


class TestMetricsCollector:
    def test_record_and_summary(self):
        mc = MetricsCollector()
        for i in range(5):
            mc.record(
                AgentExecutionRecord(
                    agent="test_agent",
                    started_at=float(i),
                    finished_at=float(i + 1),
                    latency_ms=float(100 + i * 10),
                    success=i != 2,
                    fallback_used=False,
                    tokens_input=50,
                    tokens_output=20,
                    cost_usd=0.001,
                )
            )
        summary = mc.get_agent_summary("test_agent")
        assert summary["total_runs"] == 5
        assert summary["success_rate"] == 0.8  # 4/5
        assert summary["latency_ms"]["p50"] > 0
        assert summary["latency_ms"]["mean"] > 0
        assert summary["tokens"]["input_total"] == 250
        assert summary["cost_usd"]["total"] == 0.005

    def test_check_slo_ok(self):
        mc = MetricsCollector()
        for _ in range(20):
            mc.record(
                AgentExecutionRecord(
                    agent="fast_agent",
                    started_at=0.0,
                    finished_at=1.0,
                    latency_ms=100.0,
                    success=True,
                    fallback_used=False,
                )
            )
        slo = mc.check_slo("fast_agent")
        assert slo.p95_ok is True
        assert slo.success_rate_ok is True
        assert slo.all_ok is True
        assert slo.sample_count == 20

    def test_check_slo_p95_violation(self):
        mc = MetricsCollector()
        for _ in range(20):
            mc.record(
                AgentExecutionRecord(
                    agent="slow_agent",
                    started_at=0.0,
                    finished_at=1.0,
                    latency_ms=15000.0,
                    success=True,
                    fallback_used=False,
                )
            )
        slo = mc.check_slo("slow_agent")
        assert slo.p95_ok is False
        assert slo.all_ok is False

    def test_check_slo_success_rate_violation(self):
        mc = MetricsCollector()
        for i in range(20):
            mc.record(
                AgentExecutionRecord(
                    agent="flaky_agent",
                    started_at=0.0,
                    finished_at=1.0,
                    latency_ms=100.0,
                    success=i < 10,
                    fallback_used=False,
                )
            )
        slo = mc.check_slo("flaky_agent")
        assert slo.success_rate_ok is False
        assert slo.all_ok is False

    def test_check_slo_empty_buffer(self):
        mc = MetricsCollector()
        slo = mc.check_slo("no_data_agent")
        assert slo.sample_count == 0
        assert slo.all_ok is True

    def test_configure_slo(self):
        mc = MetricsCollector()
        mc.configure_slo("custom_agent", p95_latency_ms=2000.0, min_success_rate=0.99)
        for _ in range(10):
            mc.record(
                AgentExecutionRecord(
                    agent="custom_agent",
                    started_at=0.0,
                    finished_at=1.0,
                    latency_ms=1500.0,
                    success=True,
                    fallback_used=False,
                )
            )
        slo = mc.check_slo("custom_agent")
        assert slo.slo_p95_latency_ms == 2000.0
        assert slo.slo_min_success_rate == 0.99
        assert slo.all_ok is True

    def test_ring_buffer_max_size(self):
        mc = MetricsCollector()
        for i in range(600):
            mc.record(
                AgentExecutionRecord(
                    agent="bounded_agent",
                    started_at=float(i),
                    finished_at=float(i + 1),
                    latency_ms=float(i),
                    success=True,
                    fallback_used=False,
                )
            )
        summary = mc.get_agent_summary("bounded_agent")
        assert summary["total_runs"] == 500

    def test_check_all_slos(self):
        mc = MetricsCollector()
        for name in ("agent_a", "agent_b"):
            for _ in range(10):
                mc.record(
                    AgentExecutionRecord(
                        agent=name,
                        started_at=0.0,
                        finished_at=1.0,
                        latency_ms=100.0,
                        success=True,
                        fallback_used=False,
                    )
                )
        results = mc.check_all_slos()
        assert "agent_a" in results
        assert "agent_b" in results
        assert all(r.all_ok for r in results.values())

    @pytest.mark.asyncio
    async def test_track_success(self):
        mc = MetricsCollector()

        async def ok_fn(x: int) -> int:
            return x * 2

        result = await mc.track("track_agent", ok_fn, 5)
        assert result == 10
        summary = mc.get_agent_summary("track_agent")
        assert summary["total_runs"] == 1
        assert summary["success_rate"] == 1.0

    @pytest.mark.asyncio
    async def test_track_failure(self):
        mc = MetricsCollector()

        async def fail_fn() -> None:
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            await mc.track("track_agent", fail_fn)
        summary = mc.get_agent_summary("track_agent")
        assert summary["total_runs"] == 1
        assert summary["success_rate"] == 0.0

    @pytest.mark.asyncio
    async def test_track_does_not_swallow_exceptions(self):
        mc = MetricsCollector()

        async def exc_fn() -> None:
            raise RuntimeError("test")

        with pytest.raises(RuntimeError):
            await mc.track("x", exc_fn)
        summary = mc.get_agent_summary("x")
        assert summary["total_runs"] == 1


class TestSingleton:
    def test_singleton_exists(self):
        from ecommerce_ops.observability.agent_metrics import agent_metrics as m1

        from ecommerce_ops.observability.agent_metrics import agent_metrics as m2
        assert m1 is m2

    def test_singleton_buffers_independent(self):
        mc = MetricsCollector()
        mc.record(
            AgentExecutionRecord(
                agent="ind",
                started_at=0.0,
                finished_at=1.0,
                latency_ms=100.0,
                success=True,
                fallback_used=False,
            )
        )
        assert mc.get_agent_summary("ind")["total_runs"] == 1


class TestFactoryInstrumentation:
    """Verify UnifiedAgent.run() emits MetricsCollector records."""

    @pytest.mark.asyncio
    async def test_rule_based_agent_records_metrics(self):
        from ecommerce_ops.agents.factory import UnifiedAgent

        rule = MagicMock()

        async def _run(state):
            return {"decisions": [], "status": "ok"}

        rule.run = _run
        rule.create_decision.return_value = {"action_type": "TEST"}

        agent = UnifiedAgent(
            name="test_unified",
            llm_agent=None,
            rule_agent=rule,
            llm_method=None,
            rule_method="run",
            input_adapter=None,
            output_adapter=None,
        )

        state = {"decisions": []}
        agent_metrics._buffers.pop("test_unified", None)

        result = await agent.run(state)
        assert result["status"] == "ok"

        summary = agent_metrics.get_agent_summary("test_unified")
        assert summary["total_runs"] == 1
        assert summary["success_rate"] == 1.0
        assert summary["latency_ms"]["p50"] >= 0

    @pytest.mark.asyncio
    async def test_rule_based_failure_records_error(self):
        from ecommerce_ops.agents.factory import UnifiedAgent

        rule = MagicMock()

        async def _run(state):
            raise RuntimeError("fail")

        rule.run = _run

        agent = UnifiedAgent(
            name="fail_unified",
            llm_agent=None,
            rule_agent=rule,
            llm_method=None,
            rule_method="run",
            input_adapter=None,
            output_adapter=None,
        )

        agent_metrics._buffers.pop("fail_unified", None)
        state = {"decisions": []}
        result = await agent.run(state)

        assert "fail_unified" in [e.get("agent") for e in result.get("errors", [])]
        summary = agent_metrics.get_agent_summary("fail_unified")
        assert summary["total_runs"] == 1
        assert summary["success_rate"] == 0.0


class TestPrometheusEmission:
    def test_emit_prometheus_does_not_crash(self):
        from ecommerce_ops.observability.agent_metrics import _emit_prometheus

        record = AgentExecutionRecord(
            agent="promo_agent",
            started_at=0.0,
            finished_at=1.0,
            latency_ms=500.0,
            success=True,
            fallback_used=False,
            tokens_input=100,
            tokens_output=50,
            cost_usd=0.001,
        )
        _emit_prometheus("promo_agent", record)
