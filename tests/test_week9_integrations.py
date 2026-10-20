"""Week 9: email (Resend), Slack webhook URL, outbound webhooks, multi-store scoping."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from pydantic import SecretStr

from ecommerce_ops.api.metrics import METRIC_OUTBOUND_WEBHOOKS
from ecommerce_ops.config import settings
from ecommerce_ops.infra.email import email_enabled, notify_email, send_email
from ecommerce_ops.infra.notifications import _send_slack, notify_daily_summary
from ecommerce_ops.infra.outbound_webhooks import (
    _matches,
    dispatch_outbound_webhook,
    sign_payload,
)


class _FakeSession:
    """Async-context session returning fixed webhook rows for any select."""

    def __init__(self, rows):
        self._rows = rows
        self.executed = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, stmt):
        self.executed.append(stmt)
        result = MagicMock()
        result.scalars.return_value.all.return_value = self._rows
        return result


def _fake_session_factory(rows):
    return _FakeSessionFactory(rows)


class _FakeSessionFactory:
    def __init__(self, rows):
        self._rows = rows

    def __call__(self):
        return _FakeSession(self._rows)

# ── outbound_webhooks (signing / matching) ─────────────────


class TestSignPayload:
    def test_hmac_sha256_hex(self):
        body = b'{"a":1}'
        digest = sign_payload(body, "secret-key")
        assert len(digest) == 64
        assert digest == sign_payload(body, "secret-key")
        assert digest != sign_payload(body, "other-secret")
        assert digest != sign_payload(b'{"a":2}', "secret-key")


class TestMatches:
    def test_wildcard_matches_everything(self):
        assert _matches(["*"], "hitl_request") is True
        assert _matches(["*"], "daily_summary") is True

    def test_exact_event(self):
        assert _matches(["hitl_request"], "hitl_request") is True
        assert _matches(["hitl_request", "pipeline_failed"], "pipeline_failed") is True

    def test_unlisted_event(self):
        assert _matches(["hitl_request"], "agent_graduated") is False
        assert _matches([], "hitl_request") is False


@pytest.mark.asyncio
async def test_dispatch_posts_to_matching_enabled_webhook():
    hook = SimpleNamespace(
        events=["hitl_request", "daily_summary"],
        url="https://hooks.example.com/h/acct/test",
        name="test-webhook",
        secret="top-secret",
    )
    http_client = AsyncMock()
    http_client.post.return_value = SimpleNamespace(status_code=200, text="ok")
    httpx_client = AsyncMock()
    httpx_client.__aenter__.return_value = http_client
    httpx_client.__aexit__.return_value = False

    with (
        patch("ecommerce_ops.models.db.async_session_factory", _fake_session_factory([hook])),
        patch("httpx.AsyncClient", return_value=httpx_client),
    ):
        await dispatch_outbound_webhook(
            "daily_summary", {"runs": 1, "decisions": 2, "pending_hitl": 0}
        )

    http_client.post.assert_awaited_once()
    call = http_client.post.call_args
    assert call.args[0] == hook.url
    assert call.kwargs["headers"]["X-Ecom-Ops-Event"] == "daily_summary"
    signature = call.kwargs["headers"]["X-Ecom-Ops-Signature"]
    assert signature == sign_payload(call.kwargs["content"], hook.secret)


@pytest.mark.asyncio
async def test_dispatch_skips_non_matching_webhook():
    hook = SimpleNamespace(
        events=["agent_graduated"],
        url="https://hooks.example.com/h",
        name="grader",
        secret=None,
    )
    http_client = AsyncMock()
    http_client.post.return_value = SimpleNamespace(status_code=200, text="ok")
    httpx_client = AsyncMock()
    httpx_client.__aenter__.return_value = http_client
    httpx_client.__aexit__.return_value = False

    with (
        patch("ecommerce_ops.models.db.async_session_factory", _fake_session_factory([hook])),
        patch("httpx.AsyncClient", return_value=httpx_client),
    ):
        await dispatch_outbound_webhook("pipeline_failed", {"run_id": "r1"})

    http_client.post.assert_not_awaited()


@pytest.mark.asyncio
async def test_dispatch_records_failure_metric_and_survives():
    hook = SimpleNamespace(
        events=["*"],
        url="https://hooks.example.com/h",
        name="always-fails",
        secret=None,
    )
    http_client = AsyncMock()
    http_client.post.side_effect = RuntimeError("connection refused")
    httpx_client = AsyncMock()
    httpx_client.__aenter__.return_value = http_client
    httpx_client.__aexit__.return_value = False

    with (
        patch("ecommerce_ops.models.db.async_session_factory", _fake_session_factory([hook])),
        patch("httpx.AsyncClient", return_value=httpx_client),
    ):
        # Must not raise — notification fan-out is best-effort.
        await dispatch_outbound_webhook("test", {"hello": "world"})

    http_client.post.assert_awaited_once()
    assert (
        METRIC_OUTBOUND_WEBHOOKS.labels(event_type="test", result="failed")._value.get() >= 1
    )


# ── email (Resend) ────────────────────────────────────────


class TestEmail:
    def test_email_disabled_without_key(self, monkeypatch):
        monkeypatch.setattr(settings, "RESEND_API_KEY", None)
        assert email_enabled() is False

    def test_email_enabled_with_key(self, monkeypatch):
        monkeypatch.setattr(settings, "RESEND_API_KEY", SecretStr("re_abc"))
        assert email_enabled() is True

    @pytest.mark.asyncio
    async def test_send_email_noop_without_key(self, monkeypatch):
        monkeypatch.setattr(settings, "RESEND_API_KEY", None)
        with patch("httpx.AsyncClient") as mock_http:
            ok = await send_email("a@example.com", "Subject", "Body")
        assert ok is False
        mock_http.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_email_posts_to_resend(self, monkeypatch):
        monkeypatch.setattr(settings, "RESEND_API_KEY", SecretStr("re_abc"))
        monkeypatch.setattr(settings, "NOTIFY_FROM_EMAIL", "ops@example.com")

        http_client = AsyncMock()
        http_client.post.return_value = SimpleNamespace(status_code=200, text="")
        httpx_client = AsyncMock()
        httpx_client.__aenter__.return_value = http_client
        httpx_client.__aexit__.return_value = False

        with patch("httpx.AsyncClient", return_value=httpx_client):
            ok = await send_email("admin@example.com", "Test subject", "Test body")

        assert ok is True
        http_client.post.assert_awaited_once()
        call = http_client.post.call_args
        assert call.args[0] == "https://api.resend.com/emails"
        assert call.kwargs["headers"]["Authorization"] == "Bearer re_abc"
        assert call.kwargs["json"] == {
            "from": "ops@example.com",
            "to": ["admin@example.com"],
            "subject": "Test subject",
            "text": "Test body",
        }

    @pytest.mark.asyncio
    async def test_send_email_failure_returns_false(self, monkeypatch):
        monkeypatch.setattr(settings, "RESEND_API_KEY", SecretStr("re_abc"))
        http_client = AsyncMock()
        http_client.post.return_value = SimpleNamespace(status_code=422, text='{"error": "nope"}')
        httpx_client = AsyncMock()
        httpx_client.__aenter__.return_value = http_client
        httpx_client.__aexit__.return_value = False

        with patch("httpx.AsyncClient", return_value=httpx_client):
            ok = await send_email("admin@example.com", "S", "B")

        assert ok is False

    @pytest.mark.asyncio
    async def test_notify_email_noop_without_recipient(self, monkeypatch):
        monkeypatch.setattr(settings, "NOTIFY_EMAIL", None)
        with patch("ecommerce_ops.infra.email.send_email", new_callable=AsyncMock) as send:
            ok = await notify_email("Subject", "Body")
        assert ok is False
        send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_notify_email_dispatches_to_operator(self, monkeypatch):
        monkeypatch.setattr(settings, "NOTIFY_EMAIL", "ops@example.com")
        with patch("ecommerce_ops.infra.email.send_email", new_callable=AsyncMock) as send:
            send.return_value = True
            ok = await notify_email("Subject", "Body")
        assert ok is True
        send.assert_awaited_once_with(
            to="ops@example.com", subject="Subject", text_body="Body"
        )


# ── Slack delivery ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_slack_webhook_url_preferred(monkeypatch):
    monkeypatch.setattr(settings, "SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/T/B/X")
    monkeypatch.setattr(settings, "SLACK_BOT_TOKEN", None)

    http_client = AsyncMock()
    http_client.post.return_value = SimpleNamespace(status_code=200, text="")
    httpx_client = AsyncMock()
    httpx_client.__aenter__.return_value = http_client
    httpx_client.__aexit__.return_value = False

    with patch("httpx.AsyncClient", return_value=httpx_client):
        await _send_slack("hello from ops")

    http_client.post.assert_awaited_once()
    call = http_client.post.call_args
    assert call.args[0] == "https://hooks.slack.com/services/T/B/X"
    assert call.kwargs["json"] == {"text": "hello from ops"}


@pytest.mark.asyncio
async def test_slack_bot_token_used_without_webhook(monkeypatch):
    monkeypatch.setattr(settings, "SLACK_WEBHOOK_URL", None)
    monkeypatch.setattr(settings, "SLACK_BOT_TOKEN", SecretStr("xoxb-token"))

    http_client = AsyncMock()
    http_client.post.return_value = SimpleNamespace(status_code=200, text="")
    httpx_client = AsyncMock()
    httpx_client.__aenter__.return_value = http_client
    httpx_client.__aexit__.return_value = False

    with patch("httpx.AsyncClient", return_value=httpx_client):
        await _send_slack("hello")

    http_client.post.assert_awaited_once()
    call = http_client.post.call_args
    assert call.args[0] == "https://slack.com/api/chat.postMessage"
    assert call.kwargs["headers"]["Authorization"] == "Bearer xoxb-token"


@pytest.mark.asyncio
async def test_slack_noop_without_any_config(monkeypatch):
    monkeypatch.setattr(settings, "SLACK_WEBHOOK_URL", None)
    monkeypatch.setattr(settings, "SLACK_BOT_TOKEN", None)
    with patch("httpx.AsyncClient") as mock_http:
        await _send_slack("hello")
    mock_http.assert_not_called()


# ── fan-out from notifications ────────────────────────────


@pytest.mark.asyncio
async def test_notify_daily_summary_fans_out_to_all_channels():
    with (
        patch("ecommerce_ops.infra.notifications._send_slack", new_callable=AsyncMock) as slack,
        patch(
            "ecommerce_ops.infra.notifications.notify_email", new_callable=AsyncMock
        ) as email,
        patch(
            "ecommerce_ops.infra.notifications.dispatch_outbound_webhook",
            new_callable=AsyncMock,
        ) as webhook,
    ):
        await notify_daily_summary({"runs": 1, "decisions": 2, "pending_hitl": 0})

    slack.assert_awaited_once()
    email.assert_awaited_once()
    email.assert_awaited_with(
        "Daily ops summary", "[DAILY] Pipeline runs: 1, decisions: 2, pending HITL: 0"
    )
    webhook.assert_awaited_once()
    assert webhook.call_args.args[0] == "daily_summary"


# ── integrations API (outbound webhook CRUD) ──────────────

AUTH = {"Authorization": "Bearer opsiq-dev-key-2024"}


def _webhook_payload(name: str) -> dict:
    return {
        "name": name,
        "url": "https://hooks.example.com/h/acct/9",
        "events": ["hitl_request", "daily_summary"],
        "enabled": True,
    }


@pytest_asyncio.fixture()
async def api_engine():
    from sqlalchemy.ext.asyncio import create_async_engine

    from ecommerce_ops.models.db import Base

    eng = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture()
async def api_session(api_engine):
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    factory = async_sessionmaker(api_engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as s:
        yield s


@pytest_asyncio.fixture()
async def api_client(api_session):
    from httpx import ASGITransport, AsyncClient

    from ecommerce_ops.api.app import app
    from ecommerce_ops.models import get_db_session

    async def _override():
        yield api_session

    app.dependency_overrides[get_db_session] = _override
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test", headers=AUTH)
    yield client
    await client.aclose()
    app.dependency_overrides.clear()


class TestWebhookAPI:
    @pytest.mark.asyncio
    async def test_crud_roundtrip(self, api_client):
        name = f"crud-{id(api_client)}"
        resp = await api_client.post(
            "/api/integrations/webhooks", json=_webhook_payload(name), headers=AUTH
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        hook_id = body["id"]
        assert body["name"] == name
        assert body["enabled"] is True

        listed = await api_client.get("/api/integrations/webhooks", headers=AUTH)
        assert listed.status_code == 200
        ids = [w["id"] for w in listed.json()["webhooks"]]
        assert hook_id in ids

        updated = await api_client.patch(
            f"/api/integrations/webhooks/{hook_id}",
            json={"enabled": False, "events": ["*"]},
            headers=AUTH,
        )
        assert updated.status_code == 200
        assert updated.json()["enabled"] is False
        assert updated.json()["events"] == ["*"]

        disabled_list = await api_client.get("/api/integrations/webhooks", headers=AUTH)
        row = next(w for w in disabled_list.json()["webhooks"] if w["id"] == hook_id)
        assert row["enabled"] is False

        deleted = await api_client.delete(
            f"/api/integrations/webhooks/{hook_id}", headers=AUTH
        )
        assert deleted.status_code == 200

        gone = await api_client.get("/api/integrations/webhooks", headers=AUTH)
        assert hook_id not in [w["id"] for w in gone.json()["webhooks"]]

    @pytest.mark.asyncio
    async def test_duplicate_name_rejected(self, api_client):
        name = f"dup-{id(api_client)}"
        first = await api_client.post(
            "/api/integrations/webhooks", json=_webhook_payload(name), headers=AUTH
        )
        assert first.status_code == 201
        hook_id = first.json()["id"]

        second = await api_client.post(
            "/api/integrations/webhooks", json=_webhook_payload(name), headers=AUTH
        )
        assert second.status_code == 409

        await api_client.delete(f"/api/integrations/webhooks/{hook_id}", headers=AUTH)

    @pytest.mark.asyncio
    async def test_non_https_url_rejected(self, api_client):
        payload = dict(_webhook_payload(f"http-test-{id(api_client)}"))
        payload["url"] = "http://insecure.example.com/h"
        resp = await api_client.post(
            "/api/integrations/webhooks", json=payload, headers=AUTH
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_unknown_event_rejected(self, api_client):
        payload = dict(_webhook_payload(f"evt-test-{id(api_client)}"))
        payload["events"] = ["not_a_real_event"]
        resp = await api_client.post(
            "/api/integrations/webhooks", json=payload, headers=AUTH
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_webhook_404(self, api_client):
        resp = await api_client.patch(
            "/api/integrations/webhooks/999999", json={"enabled": False}, headers=AUTH
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_test_endpoint(self, api_client):
        name = f"test-endpoint-{id(api_client)}"
        created = await api_client.post(
            "/api/integrations/webhooks", json=_webhook_payload(name), headers=AUTH
        )
        hook_id = created.json()["id"]

        with patch(
            "ecommerce_ops.api.integrations.send_test_webhook", new_callable=AsyncMock
        ) as send:
            send.return_value = True
            resp = await api_client.post(
                f"/api/integrations/webhooks/{hook_id}/test", headers=AUTH
            )
        assert resp.status_code == 200
        send.assert_awaited_once_with(hook_id)

        await api_client.delete(f"/api/integrations/webhooks/{hook_id}", headers=AUTH)
