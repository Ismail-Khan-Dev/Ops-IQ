import pytest
from httpx import ASGITransport, AsyncClient

from ecommerce_ops.api.app import app

API_KEY = "opsiq-dev-key-2024"

@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_login_invalid_key(client):
    resp = await client.post("/api/auth/login", json={"api_key": "wrong-key"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_valid_key(client):
    resp = await client.post("/api/auth/login", json={"api_key": API_KEY})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["operator"] == "api-operator"


@pytest.mark.asyncio
async def test_login_with_operator(client):
    resp = await client.post("/api/auth/login", json={"api_key": API_KEY, "operator_id": "test-op"})
    assert resp.status_code == 200
    assert resp.json()["operator"] == "test-op"


@pytest.mark.asyncio
async def test_missing_auth_on_protected_route(client):
    resp = await client.post("/api/approvals/fake-id/approve", json={})
    # Should fail with 401 because no Bearer token
    assert resp.status_code in (401, 404)


@pytest.mark.asyncio
async def test_valid_auth_on_protected_route(client):
    headers = {"Authorization": f"Bearer {API_KEY}"}
    resp = await client.post("/api/approvals/fake-id/approve", json={}, headers=headers)
    # Valid auth but action doesn't exist -> 404 (auth passed)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_health_without_auth(client):
    resp = await client.get("/health")
    assert resp.status_code in (200, 503)


@pytest.mark.asyncio
async def test_protected_endpoints_require_auth(client):
    """Content APIs must reject anonymous requests (default-deny)."""
    endpoints = [
        "/api/approvals",
        "/api/agents/status",
        "/api/analytics",
        "/api/audit",
        "/api/settings",
    ]
    for ep in endpoints:
        resp = await client.get(ep)
        assert resp.status_code == 401, f"{ep} returned {resp.status_code}"

    resp = await client.get("/api/audit/export?format=json")
    assert resp.status_code == 401

    resp = await client.post("/api/run")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_public_paths_stay_open(client):
    """Infrastructure endpoints remain reachable without auth."""
    for ep in ["/health", "/live", "/ready"]:
        resp = await client.get(ep)
        assert resp.status_code in (200, 503), f"{ep} returned {resp.status_code}"


@pytest.mark.asyncio
async def test_metrics_requires_auth_outside_dev(client):
    """/metrics is auth-gated outside development to hide internal metrics."""
    without_auth = await client.get("/metrics")
    assert without_auth.status_code == 401

    with_auth = await client.get(
        "/metrics",
        headers={"Authorization": f"Bearer {API_KEY}"},
    )
    assert with_auth.status_code == 200
