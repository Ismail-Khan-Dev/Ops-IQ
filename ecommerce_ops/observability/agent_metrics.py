"""Per-agent instrumentation for latency, success-rate, cost, and SLO checks.

Usage::

    from ecommerce_ops.observability.agent_metrics import agent_metrics

    # Wrap any async callable (typically UnifiedAgent.run)
    result = await agent_metrics.track("fraud", my_agent.run, state)

The collector emits Prometheus counters/histograms and keeps a bounded
in-memory ring buffer so SLO checks (p95 latency, success rate) are
available without a database round-trip.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Deque, Dict, Optional

from ecommerce_ops.utils import utc_now

logger = logging.getLogger("ecommerce_ops.observability.agent_metrics")

# ── SLO defaults (configurable at runtime) ─────────────────

DEFAULT_SLO: Dict[str, Dict[str, float]] = {
    "fraud": {"p95_latency_ms": 5000.0, "min_success_rate": 0.95},
    "inventory": {"p95_latency_ms": 5000.0, "min_success_rate": 0.95},
    "marketing": {"p95_latency_ms": 8000.0, "min_success_rate": 0.90},
    "pricing": {"p95_latency_ms": 3000.0, "min_success_rate": 0.98},
    "reviews": {"p95_latency_ms": 5000.0, "min_success_rate": 0.95},
    "__default__": {"p95_latency_ms": 10000.0, "min_success_rate": 0.90},
}

_RING_BUFFER_SIZE = 500  # last N executions per agent


# ── Per-agent execution record ─────────────────────────────

@dataclass
class AgentExecutionRecord:
    """Immutable record of a single agent execution."""

    agent: str
    started_at: float  # time.monotonic()
    finished_at: float
    latency_ms: float
    success: bool
    fallback_used: bool
    tokens_input: int = 0
    tokens_output: int = 0
    cost_usd: float = 0.0
    error: Optional[str] = None
    decision_type: Optional[str] = None
    confidence: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent": self.agent,
            "latency_ms": round(self.latency_ms, 2),
            "success": self.success,
            "fallback_used": self.fallback_used,
            "tokens_input": self.tokens_input,
            "tokens_output": self.tokens_output,
            "cost_usd": round(self.cost_usd, 6),
            "error": self.error,
            "decision_type": self.decision_type,
            "confidence": self.confidence,
            "wall_time": utc_now().isoformat(),
        }


# ── SLO check result ──────────────────────────────────────

@dataclass
class SLOResult:
    """Result of an SLO check for one agent."""

    agent: str
    p95_latency_ms: float
    slo_p95_latency_ms: float
    p95_ok: bool
    success_rate: float
    slo_min_success_rate: float
    success_rate_ok: bool
    sample_count: int
    all_ok: bool = field(init=False)

    def __post_init__(self) -> None:
        self.all_ok = self.p95_ok and self.success_rate_ok


# ── Prometheus counters (lazy import to avoid circular) ────

def _emit_prometheus(agent: str, record: AgentExecutionRecord) -> None:
    """Emit Prometheus metrics for a completed execution."""
    try:
        from ecommerce_ops.api.metrics import (
            METRIC_AGENT_EXECUTION_ERRORS,
            METRIC_AGENT_FALLBACK_TOTAL,
            METRIC_AGENT_RUNS_TOTAL,
            METRIC_LLM_COST_DOLLARS,
            METRIC_LLM_TOKENS_INPUT,
            METRIC_LLM_TOKENS_OUTPUT,
        )

        status = "success" if record.success else "error"
        METRIC_AGENT_RUNS_TOTAL.labels(agent=agent, status=status).inc()
        if record.fallback_used:
            METRIC_AGENT_FALLBACK_TOTAL.labels(agent=agent).inc()
        METRIC_AGENT_EXECUTION_ERRORS.labels(agent=agent).inc(
            0 if record.success else 1
        )
        if record.tokens_input > 0:
            METRIC_LLM_TOKENS_INPUT.labels(agent=agent, model="").inc(
                record.tokens_input
            )
        if record.tokens_output > 0:
            METRIC_LLM_TOKENS_OUTPUT.labels(agent=agent, model="").inc(
                record.tokens_output
            )
        if record.cost_usd > 0:
            METRIC_LLM_COST_DOLLARS.labels(agent=agent, model="").inc(
                record.cost_usd
            )
        # Log structured decision record
        logger.info(
            "AGENT_DECISION agent=%s status=%s latency_ms=%.1f "
            "fallback=%s tokens_in=%d tokens_out=%d cost=$%.4f "
            "decision=%s confidence=%s",
            agent,
            status,
            record.latency_ms,
            record.fallback_used,
            record.tokens_input,
            record.tokens_output,
            record.cost_usd,
            record.decision_type or "unknown",
            f"{record.confidence:.2f}" if record.confidence is not None else "n/a",
        )
    except Exception:
        pass


# ── MetricsCollector (singleton) ───────────────────────────

class MetricsCollector:
    """Collects per-agent execution metrics and computes SLOs.

    Thread-safe: all mutations go through a deque (atomic append/pop).
    """

    def __init__(self) -> None:
        self._buffers: Dict[str, Deque[AgentExecutionRecord]] = {}
        self._slo_config: Dict[str, Dict[str, float]] = dict(DEFAULT_SLO)

    def configure_slo(
        self, agent: str, p95_latency_ms: float, min_success_rate: float
    ) -> None:
        """Override SLO thresholds for a specific agent at runtime."""
        self._slo_config[agent] = {
            "p95_latency_ms": p95_latency_ms,
            "min_success_rate": min_success_rate,
        }

    def _buffer(self, agent: str) -> Deque[AgentExecutionRecord]:
        if agent not in self._buffers:
            self._buffers[agent] = deque(maxlen=_RING_BUFFER_SIZE)
        return self._buffers[agent]

    def record(self, record: AgentExecutionRecord) -> None:
        """Append a completed execution record."""
        buf = self._buffer(record.agent)
        buf.append(record)
        _emit_prometheus(record.agent, record)

    async def track(
        self,
        agent: str,
        fn: Callable[..., Coroutine[Any, Any, Any]],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Wrap an async callable with timing and metric recording.

        Returns whatever ``fn`` returns. On exception, records a failed
        execution and re-raises.
        """
        start = time.monotonic()
        success = True
        error: Optional[str] = None
        result: Any = None
        try:
            result = await fn(*args, **kwargs)
            return result
        except Exception as exc:
            success = False
            error = str(exc)[:200]
            raise
        finally:
            elapsed_ms = (time.monotonic() - start) * 1000
            record = AgentExecutionRecord(
                agent=agent,
                started_at=start,
                finished_at=time.monotonic(),
                latency_ms=elapsed_ms,
                success=success,
                fallback_used=False,
                error=error,
            )
            self.record(record)

    def check_slo(self, agent: str) -> SLOResult:
        """Compute SLO status for *agent* from the in-memory ring buffer."""
        buf = self._buffers.get(agent)
        if not buf or len(buf) == 0:
            return SLOResult(
                agent=agent,
                p95_latency_ms=0.0,
                slo_p95_latency_ms=self._slo_config.get(
                    agent, self._slo_config["__default__"]
                )["p95_latency_ms"],
                p95_ok=True,
                success_rate=1.0,
                slo_min_success_rate=self._slo_config.get(
                    agent, self._slo_config["__default__"]
                )["min_success_rate"],
                success_rate_ok=True,
                sample_count=0,
            )

        records = list(buf)
        latencies = sorted(r.latency_ms for r in records)
        idx = max(0, int(len(latencies) * 0.95) - 1)
        p95 = latencies[idx]
        successes = sum(1 for r in records if r.success)
        success_rate = successes / len(records)

        slo = self._slo_config.get(agent, self._slo_config["__default__"])
        return SLOResult(
            agent=agent,
            p95_latency_ms=round(p95, 2),
            slo_p95_latency_ms=slo["p95_latency_ms"],
            p95_ok=p95 <= slo["p95_latency_ms"],
            success_rate=round(success_rate, 4),
            slo_min_success_rate=slo["min_success_rate"],
            success_rate_ok=success_rate >= slo["min_success_rate"],
            sample_count=len(records),
        )

    def check_all_slos(self) -> Dict[str, SLOResult]:
        """SLO status for every agent that has data."""
        return {agent: self.check_slo(agent) for agent in self._buffers}

    def get_agent_summary(self, agent: str) -> Dict[str, Any]:
        """Aggregate stats for an agent from the ring buffer."""
        buf = self._buffers.get(agent)
        if not buf:
            return {"agent": agent, "total_runs": 0}
        records = list(buf)
        latencies = [r.latency_ms for r in records]
        costs = [r.cost_usd for r in records]
        tokens_in = [r.tokens_input for r in records]
        tokens_out = [r.tokens_output for r in records]
        successes = sum(1 for r in records if r.success)
        fallbacks = sum(1 for r in records if r.fallback_used)
        latencies_sorted = sorted(latencies)
        n = len(latencies_sorted)
        return {
            "agent": agent,
            "total_runs": n,
            "success_rate": round(successes / n, 4) if n else 0.0,
            "fallback_rate": round(fallbacks / n, 4) if n else 0.0,
            "latency_ms": {
                "p50": round(latencies_sorted[n // 2], 2) if n else 0.0,
                "p95": round(
                    latencies_sorted[max(0, int(n * 0.95) - 1)], 2
                )
                if n
                else 0.0,
                "p99": round(
                    latencies_sorted[max(0, int(n * 0.99) - 1)], 2
                )
                if n
                else 0.0,
                "mean": round(sum(latencies) / n, 2) if n else 0.0,
                "max": round(max(latencies), 2) if n else 0.0,
            },
            "cost_usd": {
                "total": round(sum(costs), 6),
                "mean": round(sum(costs) / n, 6) if n else 0.0,
            },
            "tokens": {
                "input_total": sum(tokens_in),
                "output_total": sum(tokens_out),
            },
        }


# Singleton
agent_metrics = MetricsCollector()
