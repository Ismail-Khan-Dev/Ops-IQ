"""Tests for infra/ (notifications, browser_pool, redis_task_queue) and utils.py."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ecommerce_ops.infra.browser_pool import BrowserPageSession, BrowserPool
from ecommerce_ops.infra.notifications import (
    notify_agent_graduated,
    notify_daily_summary,
    notify_hitl_request,
    notify_pipeline_failed,
)
from ecommerce_ops.utils import retry_async

# ── utils.py tests ─────────────────────────────────────────


class TestRetryAsync:
    @pytest.mark.asyncio
    async def test_succeeds_first_try(self):
        call_count = 0

        async def success_func():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await retry_async(success_func, max_retries=3)()
        assert result == "ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_failure(self):
        call_count = 0

        async def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("fail")
            return "ok"

        with patch("ecommerce_ops.utils.asyncio.sleep", new_callable=AsyncMock):
            result = await retry_async(flaky_func, max_retries=3, base_delay=0.01)()
        assert result == "ok"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_raises_after_max_retries(self):
        async def always_fail():
            raise ValueError("always")

        with (
            patch("ecommerce_ops.utils.asyncio.sleep", new_callable=AsyncMock),
            pytest.raises(ValueError, match="always"),
        ):
            await retry_async(always_fail, max_retries=2, base_delay=0.01)()

    @pytest.mark.asyncio
    async def test_only_catches_specified_exceptions(self):
        async def type_error_func():
            raise TypeError("type err")

        with pytest.raises(TypeError):
            await retry_async(type_error_func, max_retries=3, exceptions=(ValueError,))()


# ── notifications.py tests ─────────────────────────────────


class TestNotifications:
    @pytest.mark.asyncio
    async def test_notify_hitl_request(self):
        with patch("ecommerce_ops.infra.notifications.ws_manager") as mock_ws:
            mock_ws.broadcast = AsyncMock()
            with patch("ecommerce_ops.infra.notifications.settings") as mock_settings:
                mock_settings.SLACK_BOT_TOKEN = None
                await notify_hitl_request("FraudAgent", "act-1", "fraud_hold", "high", 0.9)
                mock_ws.broadcast.assert_called_once()
                call_args = mock_ws.broadcast.call_args[0][0]
                assert call_args["type"] == "notification"
                assert call_args["payload"]["kind"] == "hitl_request"

    @pytest.mark.asyncio
    async def test_notify_pipeline_failed(self):
        with patch("ecommerce_ops.infra.notifications.ws_manager") as mock_ws:
            mock_ws.broadcast = AsyncMock()
            with patch("ecommerce_ops.infra.notifications.settings") as mock_settings:
                mock_settings.SLACK_BOT_TOKEN = None
                await notify_pipeline_failed("run-123", "timeout error")
                mock_ws.broadcast.assert_called_once()
                call_args = mock_ws.broadcast.call_args[0][0]
                assert call_args["payload"]["kind"] == "pipeline_failed"

    @pytest.mark.asyncio
    async def test_notify_agent_graduated(self):
        with patch("ecommerce_ops.infra.notifications.ws_manager") as mock_ws:
            mock_ws.broadcast = AsyncMock()
            with patch("ecommerce_ops.infra.notifications.settings") as mock_settings:
                mock_settings.SLACK_BOT_TOKEN = None
                await notify_agent_graduated("PricingAgent", "autonomous", 50)
                mock_ws.broadcast.assert_called_once()
                call_args = mock_ws.broadcast.call_args[0][0]
                assert call_args["payload"]["kind"] == "agent_graduated"

    @pytest.mark.asyncio
    async def test_notify_daily_summary(self):
        with patch("ecommerce_ops.infra.notifications.ws_manager") as mock_ws:
            mock_ws.broadcast = AsyncMock()
            with patch("ecommerce_ops.infra.notifications.settings") as mock_settings:
                mock_settings.SLACK_BOT_TOKEN = None
                await notify_daily_summary({"runs": 5, "decisions": 20, "pending_hitl": 3})
                # daily_summary doesn't broadcast, just logs


# ── browser_pool.py tests ──────────────────────────────────


class TestBrowserPool:
    def test_init_defaults(self):
        pool = BrowserPool()
        assert pool._max_contexts == 3
        assert pool._headless is True
        assert pool._browser is None

    def test_init_custom(self):
        pool = BrowserPool(max_contexts=5, headless=False)
        assert pool._max_contexts == 5
        assert pool._headless is False

    @pytest.mark.asyncio
    async def test_stop_when_not_started(self):
        pool = BrowserPool()
        await pool.stop()
        assert pool._browser is None

    @pytest.mark.asyncio
    async def test_stop_decrements_refcount(self):
        pool = BrowserPool()
        pool._ref_count = 2
        pool._closed = False
        await pool.stop()
        assert pool._ref_count == 1


class TestBrowserPageSession:
    @pytest.mark.asyncio
    async def test_close_releases_semaphore(self):
        sem = MagicMock()
        ctx = AsyncMock()
        session = BrowserPageSession(ctx, MagicMock(), sem)
        await session.close()
        sem.release.assert_called_once()
