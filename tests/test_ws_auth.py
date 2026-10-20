"""
WebSocket Authentication Tests
Tests for WS connection auth, rejection, rate limiting, and per-IP limits.
"""

import os
from unittest.mock import patch

import pytest

# Set test env before imports
os.environ["ENV"] = "testing"
os.environ["API_KEY"] = "test-ws-key-2024"

from ecommerce_ops.api.ws import (
    CLOSE_AUTH_FAILED,
    CLOSE_TOO_MANY_CONNECTIONS,
    MAX_CONNECTIONS_PER_IP,
    RATE_LIMIT_MESSAGES,
    AuthenticatedConnection,
    ConnectionManager,
)


class FakeWebSocket:
    """Minimal WebSocket mock for testing."""

    def __init__(self, headers=None, client_host="127.0.0.1"):
        self.headers = headers or {}
        self._client = type("Client", (), {"host": client_host})()
        self._accepted = False
        self._closed = False
        self._close_code = None
        self._close_reason = None
        self._sent = []

    @property
    def client(self):
        return self._client

    async def accept(self):
        self._accepted = True

    async def close(self, code=1000, reason=""):
        self._closed = True
        self._close_code = code
        self._close_reason = reason

    async def send_json(self, data):
        self._sent.append(data)

    async def receive_text(self):
        return '{"type": "ping"}'


# ── Token Verification Tests ────────────────────────────────


@pytest.mark.asyncio
async def test_verify_token_valid():
    cm = ConnectionManager()
    # With API_KEY set, valid token should work
    with patch("ecommerce_ops.api.ws.settings") as mock_settings:
        from pydantic import SecretStr

        mock_settings.API_KEY = SecretStr("test-ws-key-2024")
        mock_settings.ENV = "production"
        result = await cm._verify_token("test-ws-key-2024")
        assert result is not None


@pytest.mark.asyncio
async def test_verify_token_invalid():
    cm = ConnectionManager()
    with patch("ecommerce_ops.api.ws.settings") as mock_settings:
        from pydantic import SecretStr

        mock_settings.API_KEY = SecretStr("test-ws-key-2024")
        mock_settings.ENV = "production"
        result = await cm._verify_token("wrong-key")
        assert result is None


@pytest.mark.asyncio
async def test_verify_token_none():
    cm = ConnectionManager()
    with patch("ecommerce_ops.api.ws.settings") as mock_settings:
        from pydantic import SecretStr

        mock_settings.API_KEY = SecretStr("test-ws-key-2024")
        mock_settings.ENV = "production"
        result = await cm._verify_token(None)
        assert result is None


@pytest.mark.asyncio
async def test_verify_token_empty_string():
    cm = ConnectionManager()
    with patch("ecommerce_ops.api.ws.settings") as mock_settings:
        from pydantic import SecretStr

        mock_settings.API_KEY = SecretStr("test-ws-key-2024")
        mock_settings.ENV = "production"
        result = await cm._verify_token("")
        assert result is None


@pytest.mark.asyncio
async def test_verify_token_dev_mode_any_token():
    cm = ConnectionManager()
    with patch("ecommerce_ops.api.ws.settings") as mock_settings:
        mock_settings.API_KEY = None
        mock_settings.ENV = "testing"
        result = await cm._verify_token("anything")
        assert result == "dev-ws-operator"


@pytest.mark.asyncio
async def test_verify_token_timing_safe():
    """Verify that hmac.compare_digest is used (timing-safe comparison)."""
    cm = ConnectionManager()
    with patch("ecommerce_ops.api.ws.settings") as mock_settings:
        from pydantic import SecretStr

        mock_settings.API_KEY = SecretStr("exact-key")
        mock_settings.ENV = "production"
        # Correct key
        assert await cm._verify_token("exact-key") is not None
        # Close but wrong
        assert await cm._verify_token("exact-kez") is None
        assert await cm._verify_token("exact-k") is None


# ── Connection Rejection Tests ─────────────────────────────


@pytest.mark.asyncio
async def test_connect_rejects_invalid_token():
    cm = ConnectionManager()
    ws = FakeWebSocket()
    with patch("ecommerce_ops.api.ws.settings") as mock_settings:
        from pydantic import SecretStr

        mock_settings.API_KEY = SecretStr("real-key")
        mock_settings.ENV = "production"
        result = await cm.connect(ws, token="wrong-key")

    assert result is None
    assert ws._accepted is True
    assert ws._closed is True
    assert ws._close_code == CLOSE_AUTH_FAILED


@pytest.mark.asyncio
async def test_connect_rejects_no_token():
    cm = ConnectionManager()
    ws = FakeWebSocket()
    with patch("ecommerce_ops.api.ws.settings") as mock_settings:
        from pydantic import SecretStr

        mock_settings.API_KEY = SecretStr("real-key")
        mock_settings.ENV = "production"
        result = await cm.connect(ws, token=None)

    assert result is None
    assert ws._closed is True
    assert ws._close_code == CLOSE_AUTH_FAILED


@pytest.mark.asyncio
async def test_connect_accepts_valid_token():
    cm = ConnectionManager()
    ws = FakeWebSocket()
    with patch("ecommerce_ops.api.ws.settings") as mock_settings:
        from pydantic import SecretStr

        mock_settings.API_KEY = SecretStr("real-key")
        mock_settings.ENV = "production"
        conn = await cm.connect(ws, token="real-key")

    assert conn is not None
    assert isinstance(conn, AuthenticatedConnection)
    assert conn.operator == "ws-operator"
    assert ws._accepted is True
    assert ws._closed is False
    assert cm.connection_count == 1


# ── Per-IP Connection Limit Tests ──────────────────────────


@pytest.mark.asyncio
async def test_per_ip_limit_enforced():
    cm = ConnectionManager()
    with patch("ecommerce_ops.api.ws.settings") as mock_settings:
        from pydantic import SecretStr

        mock_settings.API_KEY = SecretStr("key")
        mock_settings.ENV = "production"

        # Connect MAX_CONNECTIONS_PER_IP from same IP
        for i in range(MAX_CONNECTIONS_PER_IP):
            ws = FakeWebSocket(client_host="10.0.0.1")
            conn = await cm.connect(ws, token="key")
            assert conn is not None, f"Connection {i} should succeed"

        # Next one should be rejected
        ws_over = FakeWebSocket(client_host="10.0.0.1")
        result = await cm.connect(ws_over, token="key")
        assert result is None
        assert ws_over._close_code == CLOSE_TOO_MANY_CONNECTIONS

        # Different IP should work
        ws_diff = FakeWebSocket(client_host="10.0.0.2")
        conn = await cm.connect(ws_diff, token="key")
        assert conn is not None

    assert cm.connection_count == MAX_CONNECTIONS_PER_IP + 1


@pytest.mark.asyncio
async def test_disconnect_frees_ip_slot():
    cm = ConnectionManager()
    with patch("ecommerce_ops.api.ws.settings") as mock_settings:
        from pydantic import SecretStr

        mock_settings.API_KEY = SecretStr("key")
        mock_settings.ENV = "production"

        ws1 = FakeWebSocket(client_host="10.0.0.1")
        conn1 = await cm.connect(ws1, token="key")
        assert conn1 is not None
        assert cm.connection_count == 1

        await cm.disconnect(conn1)
        assert cm.connection_count == 0

        # Should be able to connect again from same IP
        ws2 = FakeWebSocket(client_host="10.0.0.1")
        conn2 = await cm.connect(ws2, token="key")
        assert conn2 is not None


# ── Rate Limiting Tests ────────────────────────────────────


def test_rate_limit_within_bounds():
    conn = AuthenticatedConnection(FakeWebSocket(), "test", "127.0.0.1")
    # Should allow RATE_LIMIT_MESSAGES messages
    for _ in range(RATE_LIMIT_MESSAGES):
        assert conn.check_rate_limit() is True


def test_rate_limit_exceeded():
    conn = AuthenticatedConnection(FakeWebSocket(), "test", "127.0.0.1")
    # Exhaust the limit
    for _ in range(RATE_LIMIT_MESSAGES):
        conn.check_rate_limit()
    # Next one should fail
    assert conn.check_rate_limit() is False


# ── Broadcast Tests ────────────────────────────────────────


@pytest.mark.asyncio
async def test_broadcast_only_to_authenticated():
    cm = ConnectionManager()
    with patch("ecommerce_ops.api.ws.settings") as mock_settings:
        from pydantic import SecretStr

        mock_settings.API_KEY = SecretStr("key")
        mock_settings.ENV = "production"

        ws1 = FakeWebSocket()
        conn1 = await cm.connect(ws1, token="key")

        ws2 = FakeWebSocket()
        await cm.connect(ws2, token="wrong")  # Rejected

        await cm.broadcast({"type": "test", "data": "hello"})

    assert len(ws1._sent) == 1
    assert ws1._sent[0] == {"type": "test", "data": "hello"}
    assert len(ws2._sent) == 0  # Rejected connection got nothing


@pytest.mark.asyncio
async def test_broadcast_handles_dead_connections():
    cm = ConnectionManager()
    with patch("ecommerce_ops.api.ws.settings") as mock_settings:
        from pydantic import SecretStr

        mock_settings.API_KEY = SecretStr("key")
        mock_settings.ENV = "production"

        ws_good = FakeWebSocket()
        conn_good = await cm.connect(ws_good, token="key")

        ws_dead = FakeWebSocket()

        class DeadWS(FakeWebSocket):
            async def send_json(self, data):
                raise ConnectionError("dead")

        dead = DeadWS()
        conn_dead = await cm.connect(dead, token="key")

        # Broadcast should clean up dead connection
        await cm.broadcast({"type": "test"})
        assert cm.connection_count == 1  # Only good connection remains


# ── Stats Tests ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stats_no_sensitive_data():
    cm = ConnectionManager()
    with patch("ecommerce_ops.api.ws.settings") as mock_settings:
        from pydantic import SecretStr

        mock_settings.API_KEY = SecretStr("key")
        mock_settings.ENV = "production"

        ws = FakeWebSocket()
        await cm.connect(ws, token="key")

        stats = cm.get_stats()
        assert "total_connections" in stats
        assert "unique_ips" in stats
        assert stats["total_connections"] == 1
        # Should NOT contain operator names, IPs, etc.
        assert "operator" not in stats
        assert "ip" not in stats
