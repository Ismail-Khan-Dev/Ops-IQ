import os
from unittest.mock import MagicMock

os.environ.setdefault("ENV", "testing")
os.environ.setdefault("API_KEY", "opsiq-dev-key-2024")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")
os.environ.setdefault("DEEPSEEK_API_KEY", "sk-test-key")

import pytest
from httpx import ASGITransport, AsyncClient

from ecommerce_ops.api.app import app
from ecommerce_ops.security.sso import SSOManager

AUTH = {"Authorization": "Bearer opsiq-dev-key-2024"}


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test", headers=AUTH)


@pytest.mark.asyncio
async def test_sso_manager_providers_empty():
    mgr = SSOManager()
    providers = mgr.get_providers()
    assert providers == []


@pytest.mark.asyncio
async def test_sso_manager_create_auth_url_google(monkeypatch):
    mgr = SSOManager()
    monkeypatch.setattr("ecommerce_ops.security.sso.settings", MagicMock(GOOGLE_CLIENT_ID="test-google-client-id"))
    url = mgr.create_authorization_url("google")
    assert "accounts.google.com" in url
    assert "client_id=test-google-client-id" in url
    assert "response_type=code" in url
    assert "state=" in url


@pytest.mark.asyncio
async def test_sso_manager_create_auth_url_unknown():
    mgr = SSOManager()
    with pytest.raises(Exception) as exc_info:
        mgr.create_authorization_url("unknown_provider")
    assert "Unknown SSO provider" in str(exc_info.value.detail) or "Unknown SSO provider" in str(
        exc_info.value
    )


@pytest.mark.asyncio
async def test_sso_manager_validate_state_valid():
    mgr = SSOManager()
    state = "test-state-123"
    mgr._state_store[state] = "google"
    provider = mgr.validate_state(state)
    assert provider == "google"
    assert state not in mgr._state_store


@pytest.mark.asyncio
async def test_sso_manager_validate_state_invalid():
    mgr = SSOManager()
    with pytest.raises(Exception) as exc_info:
        mgr.validate_state("nonexistent-state")
    assert "Invalid or expired SSO state" in str(exc_info.value.detail) or "Invalid or expired" in str(
        exc_info.value
    )


@pytest.mark.asyncio
async def test_sso_manager_session_lifecycle():
    mgr = SSOManager()
    token = "session-token-abc"
    assert mgr.get_session(token) is None
    assert mgr.revoke_session(token) is False

    from ecommerce_ops.security.sso import SSOSession

    session = SSOSession(
        provider="google",
        user_email="test@example.com",
        user_name="Test User",
        role="viewer",
        expires_at=0,
    )
    mgr._sessions[token] = session

    retrieved = mgr.get_session(token)
    assert retrieved is not None
    assert retrieved.user_email == "test@example.com"

    assert mgr.revoke_session(token) is True
    assert mgr.get_session(token) is None
    assert mgr.revoke_session(token) is False


@pytest.mark.asyncio
async def test_sso_api_providers(client):
    resp = await client.get("/auth/sso/providers")
    assert resp.status_code == 200
    data = resp.json()
    assert "providers" in data
    assert isinstance(data["providers"], list)


@pytest.mark.asyncio
async def test_sso_api_login_unknown_provider(client):
    resp = await client.post("/auth/sso/login", json={"provider": "nonexistent"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_sso_api_callback_invalid_state(client):
    resp = await client.post(
        "/auth/sso/callback",
        json={"provider": "google", "code": "fake-code", "state": "bad-state"},
    )
    assert resp.status_code == 400
