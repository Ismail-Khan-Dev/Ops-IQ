"""
Observability API Routes
Endpoints for traces, evaluations, and metrics backed by real DB queries.
"""

import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from ecommerce_ops.agents.registry import agent_registry
from ecommerce_ops.models import (
    AgentStatus,
    ApprovalAction,
    AuditEntry,
    PipelineRun,
    async_session_factory,
)
from ecommerce_ops.observability.agent_metrics import agent_metrics
from ecommerce_ops.observability.evaluation import (
    evaluation_framework,
)
from ecommerce_ops.observability.langfuse_client import langfuse_client
from ecommerce_ops.observability.trace_models import (
    TraceAggregation,
    TraceStatus,
)
from ecommerce_ops.security.auth import require_permission
from ecommerce_ops.security.models import Permission, User
from ecommerce_ops.utils import utc_now

logger = logging.getLogger("ecommerce_ops.api.observability")

router = APIRouter(prefix="/observability", tags=["observability"])


class EvaluationRequest(BaseModel):
    agent_name: str
    decision_id: str
    decision: Dict[str, Any]
    context: Optional[Dict[str, Any]] = None
    trace_id: Optional[str] = None


class BatchEvaluationRequest(BaseModel):
    evaluations: List[EvaluationRequest]


# ── Traces ─────────────────────────────────────────────────


@router.get("/traces")
async def list_traces(
    status: Optional[TraceStatus] = None,
    agent_name: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    _: User = Depends(require_permission(Permission.OBSERVABILITY_VIEW)),
):
    """List recent pipeline traces from the PipelineRun table."""
    async with async_session_factory() as session:
        stmt = select(PipelineRun).order_by(PipelineRun.started_at.desc()).limit(limit)
        if status:
            stmt = stmt.where(PipelineRun.status == status.value)
        result = await session.execute(stmt)
        runs = result.scalars().all()

        traces = []
        for run in runs:
            traces.append(
                {
                    "trace_id": run.run_id,
                    "status": run.status,
                    "data_source": run.data_source,
                    "decisions_count": run.decisions_count,
                    "actions_count": run.actions_count,
                    "evaluation_avg_score": run.evaluation_avg_score,
                    "started_at": run.started_at.isoformat() if run.started_at else None,
                    "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                    "error": run.error,
                }
            )
        return {"traces": traces, "total": len(traces)}


@router.get("/traces/{trace_id}")
async def get_trace(
    trace_id: str,
    _: User = Depends(require_permission(Permission.OBSERVABILITY_VIEW)),
):
    """Get trace details from PipelineRun table."""
    async with async_session_factory() as session:
        result = await session.execute(select(PipelineRun).where(PipelineRun.run_id == trace_id))
        run = result.scalar_one_or_none()
        if not run:
            raise HTTPException(status_code=404, detail="Trace not found")
        return {
            "trace_id": run.run_id,
            "status": run.status,
            "data_source": run.data_source,
            "decisions_count": run.decisions_count,
            "actions_count": run.actions_count,
            "evaluation_avg_score": run.evaluation_avg_score,
            "evaluation_pass_rate": run.evaluation_pass_rate,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "error": run.error,
        }


@router.get("/traces/{trace_id}/spans")
async def get_trace_spans(
    trace_id: str,
    _: User = Depends(require_permission(Permission.OBSERVABILITY_VIEW)),
):
    """Get spans for a trace from ApprovalAction table."""
    async with async_session_factory() as session:
        result = await session.execute(select(PipelineRun).where(PipelineRun.run_id == trace_id))
        run = result.scalar_one_or_none()
        if not run:
            raise HTTPException(status_code=404, detail="Trace not found")

        # Return approval actions as spans
        actions_result = await session.execute(
            select(ApprovalAction).where(
                ApprovalAction.created_at >= run.started_at,
                ApprovalAction.created_at <= (run.finished_at or utc_now()),
            )
        )
        actions = actions_result.scalars().all()
        spans = [
            {
                "span_id": a.id,
                "name": f"{a.agent}.{a.action_type}",
                "status": a.status,
                "risk_level": a.risk_level,
                "confidence_score": a.confidence_score,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in actions
        ]
        return {"spans": spans, "total": len(spans)}


@router.get("/traces/{trace_id}/scores")
async def get_trace_scores(
    trace_id: str,
    _: User = Depends(require_permission(Permission.OBSERVABILITY_VIEW)),
):
    """Get scores for a trace from evaluation results."""
    async with async_session_factory() as session:
        result = await session.execute(select(PipelineRun).where(PipelineRun.run_id == trace_id))
        run = result.scalar_one_or_none()
        if not run:
            raise HTTPException(status_code=404, detail="Trace not found")
        return {
            "evaluation_avg_score": run.evaluation_avg_score,
            "evaluation_pass_rate": run.evaluation_pass_rate,
            "decisions_count": run.decisions_count,
        }


@router.get("/traces/{trace_id}/url")
async def get_trace_url(
    trace_id: str,
    _: User = Depends(require_permission(Permission.OBSERVABILITY_VIEW)),
):
    """Get Langfuse dashboard URL for a trace."""
    url = langfuse_client.get_trace_url(trace_id)
    return {"trace_id": trace_id, "url": url}


# ── Evaluations ────────────────────────────────────────────


@router.post("/evaluate")
async def evaluate_decision(
    req: EvaluationRequest,
    _: User = Depends(require_permission(Permission.OBSERVABILITY_VIEW)),
):
    """Evaluate a single decision."""
    result = evaluation_framework.evaluate_decision(
        agent_name=req.agent_name,
        decision_id=req.decision_id,
        decision=req.decision,
        context=req.context,
        trace_id=req.trace_id,
    )

    return result.score_breakdown


@router.post("/evaluate/batch")
async def evaluate_batch(
    req: BatchEvaluationRequest,
    _: User = Depends(require_permission(Permission.OBSERVABILITY_VIEW)),
):
    """Evaluate multiple decisions."""
    evaluation_items = [
        {
            "agent_name": e.agent_name,
            "decision_id": e.decision_id,
            "dimension": e.decision,
            "context": e.context,
            "trace_id": e.trace_id,
        }
        for e in req.evaluations
    ]

    result = evaluation_framework.evaluate_batch(evaluation_items)
    return result


@router.get("/evaluate/metrics")
async def get_metric_definitions(
    _: User = Depends(require_permission(Permission.OBSERVABILITY_VIEW)),
):
    """Get available evaluation metrics."""
    metrics = {}
    for dim, metric in evaluation_framework._metrics.items():
        metrics[dim.value] = {
            "name": metric.name,
            "dimension": metric.dimension.value,
            "metric_type": metric.metric_type.value,
            "description": metric.description,
            "min_value": metric.min_value,
            "max_value": metric.max_value,
            "weight": metric.weight,
        }
    return {"metrics": metrics}


@router.get("/evaluate/history")
async def get_evaluation_history(
    agent_name: Optional[str] = None,
    days: int = Query(7, ge=1, le=90),
    _: User = Depends(require_permission(Permission.OBSERVABILITY_VIEW)),
):
    """Get evaluation history from AuditEntry table."""
    cutoff = utc_now() - timedelta(days=days)
    async with async_session_factory() as session:
        stmt = select(AuditEntry).where(AuditEntry.timestamp >= cutoff)
        if agent_name:
            stmt = stmt.where(AuditEntry.agent == agent_name)
        stmt = stmt.order_by(AuditEntry.timestamp.desc())
        result = await session.execute(stmt)
        entries = result.scalars().all()

        evaluations = [
            {
                "id": e.id,
                "agent": e.agent,
                "action_type": e.action_type,
                "decision": e.decision,
                "confidence_score": e.confidence_score,
                "financial_impact": e.financial_impact,
                "timestamp": e.timestamp.isoformat() if e.timestamp else None,
            }
            for e in entries
        ]
        return {
            "evaluations": evaluations,
            "total": len(evaluations),
            "period_days": days,
        }


# ── Aggregations ───────────────────────────────────────────


@router.get("/metrics/summary")
async def get_metrics_summary(
    days: int = Query(7, ge=1, le=90),
    _: User = Depends(require_permission(Permission.OBSERVABILITY_VIEW)),
):
    """Get aggregated metrics summary from PipelineRun and ApprovalAction tables."""
    cutoff = utc_now() - timedelta(days=days)
    async with async_session_factory() as session:
        # Pipeline run stats
        run_result = await session.execute(
            select(
                func.count(PipelineRun.id).label("total_traces"),
                func.count(PipelineRun.id)
                .filter(PipelineRun.status == "completed")
                .label("successful"),
                func.count(PipelineRun.id).filter(PipelineRun.status == "failed").label("failed"),
                func.avg(PipelineRun.evaluation_avg_score).label("avg_score"),
            ).where(PipelineRun.started_at >= cutoff)
        )
        run_stats = run_result.one()

        # Duration stats
        duration_result = await session.execute(
            select(
                func.avg(
                    func.julianday(PipelineRun.finished_at) - func.julianday(PipelineRun.started_at)
                ).label("avg_duration_days"),
            ).where(
                PipelineRun.started_at >= cutoff,
                PipelineRun.finished_at.isnot(None),
            )
        )
        duration_stats = duration_result.one()
        avg_duration_ms = (duration_stats.avg_duration_days or 0) * 86400 * 1000

        return TraceAggregation(
            total_traces=run_stats.total_traces or 0,
            successful_traces=run_stats.successful or 0,
            failed_traces=run_stats.failed or 0,
            avg_duration_ms=round(avg_duration_ms, 2),
            p50_duration_ms=0.0,
            p95_duration_ms=0.0,
            p99_duration_ms=0.0,
            total_tokens=0,
            total_cost_usd=0.0,
            avg_score=round(float(run_stats.avg_score or 0), 3),
            traces_by_status={},
            traces_by_name={},
            cost_by_model={},
            daily_volume=[],
        )


@router.get("/metrics/agents")
async def get_agent_metrics(
    _: User = Depends(require_permission(Permission.OBSERVABILITY_VIEW)),
):
    """Get per-agent metrics from AgentStatus table."""
    async with async_session_factory() as session:
        result = await session.execute(select(AgentStatus))
        agents = result.scalars().all()
        return {
            "agents": [
                {
                    "agent_id": a.agent_id,
                    "status": a.status,
                    "streak": a.streak,
                    "autonomy_level": a.autonomy_level,
                    "total_decisions": a.total_decisions,
                    "total_approvals": a.total_approvals,
                    "total_rejections": a.total_rejections,
                    "avg_confidence": a.avg_confidence,
                }
                for a in agents
            ],
        }


@router.get("/metrics/costs")
async def get_cost_metrics(
    days: int = Query(30, ge=1, le=90),
    _: User = Depends(require_permission(Permission.OBSERVABILITY_VIEW)),
):
    """Get cost breakdown metrics from PipelineRun table."""
    cutoff = utc_now() - timedelta(days=days)
    async with async_session_factory() as session:
        result = await session.execute(
            select(
                func.sum(PipelineRun.actions_count).label("total_actions"),
                func.count(PipelineRun.id).label("total_runs"),
            ).where(PipelineRun.started_at >= cutoff)
        )
        stats = result.one()
        return {
            "period_days": days,
            "total_cost_usd": 0.0,
            "cost_by_model": {},
            "cost_by_agent": {},
            "daily_costs": [],
            "total_runs": stats.total_runs or 0,
            "total_actions": stats.total_actions or 0,
        }


# ── Per-agent SLO & live metrics ───────────────────────────


@router.get("/slos")
async def get_slos(
    _: User = Depends(require_permission(Permission.OBSERVABILITY_VIEW)),
):
    """Per-agent SLO status: p95 latency and success rate vs thresholds."""
    results = agent_metrics.check_all_slos()
    return {
        agent: {
            "p95_latency_ms": r.p95_latency_ms,
            "slo_p95_latency_ms": r.slo_p95_latency_ms,
            "p95_ok": r.p95_ok,
            "success_rate": r.success_rate,
            "slo_min_success_rate": r.slo_min_success_rate,
            "success_rate_ok": r.success_rate_ok,
            "sample_count": r.sample_count,
            "all_ok": r.all_ok,
        }
        for agent, r in results.items()
    }


@router.get("/agents/live")
async def get_live_agent_metrics(
    _: User = Depends(require_permission(Permission.OBSERVABILITY_VIEW)),
):
    """Live per-agent metrics from the in-memory ring buffer.

    Returns latency histograms, success rates, cost breakdowns,
    and SLO status for every agent that has recorded executions.
    """
    summaries = {}
    for agent in list(agent_metrics._buffers.keys()):
        summaries[agent] = agent_metrics.get_agent_summary(agent)
        slo = agent_metrics.check_slo(agent)
        summaries[agent]["slo"] = {
            "p95_ok": slo.p95_ok,
            "success_rate_ok": slo.success_rate_ok,
            "all_ok": slo.all_ok,
        }
    return {"agents": summaries, "timestamp": utc_now().isoformat()}


@router.get("/agents/{agent_name}/live")
async def get_live_agent_detail(
    agent_name: str,
    _: User = Depends(require_permission(Permission.OBSERVABILITY_VIEW)),
):
    """Live metrics for a single agent."""
    summary = agent_metrics.get_agent_summary(agent_name)
    slo = agent_metrics.check_slo(agent_name)
    summary["slo"] = {
        "p95_latency_ms": slo.p95_latency_ms,
        "slo_p95_latency_ms": slo.slo_p95_latency_ms,
        "p95_ok": slo.p95_ok,
        "success_rate": slo.success_rate,
        "slo_min_success_rate": slo.slo_min_success_rate,
        "success_rate_ok": slo.success_rate_ok,
        "sample_count": slo.sample_count,
        "all_ok": slo.all_ok,
    }
    return summary


# ── Agent Registry ────────────────────────────────────────


@router.get("/registry")
async def get_registry(
    _: User = Depends(require_permission(Permission.OBSERVABILITY_VIEW)),
):
    """List all registered agent specs from the dynamic registry."""
    from ecommerce_ops.agents.factory import agent_factory

    return {
        "agents": agent_factory.list_agents(),
        "spec_count": len(agent_registry),
        "errors": agent_registry.load_errors,
    }


@router.post("/registry/reload")
async def reload_registry(
    _: User = Depends(require_permission(Permission.OBSERVABILITY_VIEW)),
):
    """Hot-reload: re-scan YAML specs and rebuild all agents."""
    from ecommerce_ops.agents.factory import agent_factory

    result = agent_factory.reload()
    return {
        "status": "ok",
        "loaded": result["loaded"],
        "errors": result["errors"],
        "agents": result["agents"],
    }


# ── Health ─────────────────────────────────────────────────


@router.get("/health")
async def observability_health():
    """Health check for observability service."""
    return {
        "status": "healthy",
        "langfuse_enabled": langfuse_client.is_enabled,
        "evaluation_framework": "loaded",
        "timestamp": utc_now().isoformat(),
    }
