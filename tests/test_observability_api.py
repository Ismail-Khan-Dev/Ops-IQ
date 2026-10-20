"""Tests for Observability API endpoints."""

import pytest
from sqlalchemy import delete

from ecommerce_ops.security.models import Permission, Role, User


def _user() -> User:
    return User(
        id="t1",
        email="t@x.com",
        role=Role.SUPER_ADMIN,
        permissions=set(Permission),
    )


async def _clear_table(model) -> None:
    """Empty a table on the shared app engine so empty-state assertions are
    order-independent (other test files may have left rows behind)."""
    from ecommerce_ops.models import async_session_factory

    async with async_session_factory() as session:
        await session.execute(delete(model))
        await session.commit()


# ── Observability Endpoint Tests ──────────────────────────


@pytest.mark.asyncio
async def test_traces_list_empty():
    from ecommerce_ops.api.observability import list_traces
    from ecommerce_ops.models import PipelineRun

    await _clear_table(PipelineRun)

    result = await list_traces(limit=50, _=_user())
    assert result["traces"] == []
    assert result["total"] == 0


@pytest.mark.asyncio
async def test_metrics_summary_zeros():
    from ecommerce_ops.api.observability import get_metrics_summary
    from ecommerce_ops.models import PipelineRun

    await _clear_table(PipelineRun)

    result = await get_metrics_summary(days=7, _=_user())
    assert result.total_traces == 0
    assert result.total_cost_usd == 0.0


@pytest.mark.asyncio
async def test_agent_metrics_empty():
    from ecommerce_ops.api.observability import get_agent_metrics
    from ecommerce_ops.models import AgentStatus

    await _clear_table(AgentStatus)

    result = await get_agent_metrics(_=_user())
    assert result["agents"] == []


@pytest.mark.asyncio
async def test_cost_metrics_zeros():
    from ecommerce_ops.api.observability import get_cost_metrics
    from ecommerce_ops.models import PipelineRun

    await _clear_table(PipelineRun)

    result = await get_cost_metrics(days=30, _=_user())
    assert result["total_cost_usd"] == 0.0


@pytest.mark.asyncio
async def test_evaluation_history_empty():
    from ecommerce_ops.api.observability import get_evaluation_history
    from ecommerce_ops.models import AuditEntry

    await _clear_table(AuditEntry)

    result = await get_evaluation_history(days=7, _=_user())
    assert result["evaluations"] == []
    assert result["total"] == 0
