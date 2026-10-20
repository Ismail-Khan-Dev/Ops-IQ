"""
Tests for Option B: Slack Interactive HITL Bot
Covers Block Kit message generation, HMAC signature verification,
interactive approval/rejection button dispatch, in-place message updates,
and API interaction endpoints.
"""

import hashlib
import hmac
import json
import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from ecommerce_ops.api.app import app
from ecommerce_ops.infra.slack_interactive import (
    build_hitl_approval_blocks,
    build_resolved_slack_blocks,
    handle_slack_interaction,
    send_interactive_hitl_notification,
    verify_slack_signature,
)
from ecommerce_ops.models import ApprovalAction, async_session_factory
from ecommerce_ops.security.models import Role, User


@pytest.fixture
def test_client():
    return TestClient(app)


def _generate_slack_signature(body: bytes, timestamp: int, secret: str = "test_signing_secret_123") -> str:
    sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}".encode("utf-8")
    computed = hmac.new(secret.encode("utf-8"), sig_basestring, hashlib.sha256).hexdigest()
    return f"v0={computed}"


# ── 1. Slack Signature Verification Tests ────────────────────────────


def test_verify_slack_signature_valid():
    secret = "my_secret_token"
    now = int(time.time())
    body = b"payload=%7B%22type%22%3A%22block_actions%22%7D"
    sig = _generate_slack_signature(body, now, secret)

    is_valid = verify_slack_signature(
        raw_body=body,
        timestamp=str(now),
        signature=sig,
        signing_secret=secret,
    )
    assert is_valid is True


def test_verify_slack_signature_invalid_hash():
    secret = "my_secret_token"
    now = int(time.time())
    body = b"payload=something"

    is_valid = verify_slack_signature(
        raw_body=body,
        timestamp=str(now),
        signature="v0=invalid_forged_hash",
        signing_secret=secret,
    )
    assert is_valid is False


def test_verify_slack_signature_expired_timestamp():
    secret = "my_secret_token"
    # 400 seconds in the past (> 300s threshold)
    past = int(time.time()) - 400
    body = b"payload=something"
    sig = _generate_slack_signature(body, past, secret)

    is_valid = verify_slack_signature(
        raw_body=body,
        timestamp=str(past),
        signature=sig,
        signing_secret=secret,
    )
    assert is_valid is False


# ── 2. Block Kit Builder Tests ───────────────────────────────────────


def test_build_hitl_approval_blocks_layout():
    blocks = build_hitl_approval_blocks(
        action_id="act_fraud_100",
        agent="FraudAgent",
        action_type="fraud_hold",
        risk_level="high",
        confidence=0.92,
        payload={
            "order_id": "ORD-12345",
            "order_total": 1250.00,
            "risk_signals": ["international_billing_shipping_mismatch"],
            "fraud_score": 88,
        },
        impact={"financial_impact": 1250.00},
        dashboard_url="https://app.opsiq.com",
    )

    assert len(blocks) >= 4
    # Header block
    assert blocks[0]["type"] == "header"
    assert "Approval Required" in blocks[0]["text"]["text"]

    # Section with fields
    fields = blocks[1]["fields"]
    assert any("FraudAgent" in f["text"] for f in fields)
    assert any("fraud_hold" in f["text"] for f in fields)
    assert any("HIGH" in f["text"] for f in fields)

    # Actions block with interactive buttons
    action_block = next(b for b in blocks if b["type"] == "actions")
    elements = action_block["elements"]
    assert len(elements) == 3  # Approve, Reject, Review in Dashboard

    approve_btn = elements[0]
    assert approve_btn["action_id"] == "hitl_approve_action"
    assert approve_btn["value"] == "act_fraud_100"
    assert approve_btn["style"] == "primary"

    reject_btn = elements[1]
    assert reject_btn["action_id"] == "hitl_reject_action"
    assert reject_btn["value"] == "act_fraud_100"
    assert reject_btn["style"] == "danger"

    dashboard_btn = elements[2]
    assert dashboard_btn["action_id"] == "view_dashboard"
    assert "https://app.opsiq.com/approvals?id=act_fraud_100" in dashboard_btn["url"]


def test_build_resolved_slack_blocks():
    blocks = build_resolved_slack_blocks(
        action_id="act_100",
        agent="FraudAgent",
        action_type="fraud_hold",
        status="executed",
        operator="slack:@sarah.ops",
        exec_msg="Held 1 fulfillment order",
    )
    assert len(blocks) == 3
    assert blocks[0]["type"] == "header"
    assert "OpsIQ Approval Resolved" in blocks[0]["text"]["text"]
    assert "APPROVED" in blocks[2]["text"]["text"]
    assert "@sarah.ops" in blocks[2]["text"]["text"]


# ── 3. Notification Dispatch Tests ───────────────────────────────────


@pytest.mark.asyncio
async def test_send_interactive_hitl_notification_webhook():
    with patch("ecommerce_ops.infra.slack_interactive.app_settings.SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/test"), \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:

        mock_post.return_value.status_code = 200

        sent = await send_interactive_hitl_notification(
            action_id="act_test_1",
            agent="PricingAgent",
            action_type="price_change",
            risk_level="medium",
            confidence=0.85,
        )

        assert sent is True
        mock_post.assert_called_once()
        sent_body = mock_post.call_args[1]["json"]
        assert "blocks" in sent_body
        assert "text" in sent_body


# ── 4. Slack Interactive Callback Processing ─────────────────────────


@pytest.mark.asyncio
async def test_handle_slack_interaction_approve():
    # Insert pending approval action in DB
    action_id = "test_slack_act_approve_1"
    async with async_session_factory() as session:
        action = ApprovalAction(
            id=action_id,
            run_id="run_slack_1",
            agent="FraudAgent",
            action_type="fraud_hold",
            confidence_score=0.95,
            risk_level="high",
            status="pending",
            payload={"order_id": "999001"},
            shadow_mode=False,
        )
        session.add(action)
        await session.commit()

    slack_payload = {
        "user": {"id": "U987", "username": "ismail_ops"},
        "actions": [
            {
                "action_id": "hitl_approve_action",
                "value": action_id,
            }
        ],
    }

    with patch("ecommerce_ops.infra.slack_interactive.execute_shop_action", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = (True, "Held 1 fulfillment order successfully")

        response = await handle_slack_interaction(slack_payload)

        assert response.get("replace_original") is True
        assert "Approved by @ismail_ops" in response.get("text", "")

        # Verify DB action was flipped to executed
        async with async_session_factory() as session:
            refreshed = await session.get(ApprovalAction, action_id)
            assert refreshed.status == "executed"
            assert refreshed.reviewed_by == "slack:@ismail_ops"


@pytest.mark.asyncio
async def test_handle_slack_interaction_reject():
    action_id = "test_slack_act_reject_1"
    async with async_session_factory() as session:
        action = ApprovalAction(
            id=action_id,
            run_id="run_slack_2",
            agent="PricingAgent",
            action_type="price_change",
            confidence_score=0.80,
            risk_level="high",
            status="pending",
            payload={"sku": "TSHIRT-BLK", "proposed_price": 45.0},
            shadow_mode=False,
        )
        session.add(action)
        await session.commit()

    slack_payload = {
        "user": {"id": "U987", "username": "sarah_growth"},
        "actions": [
            {
                "action_id": "hitl_reject_action",
                "value": action_id,
            }
        ],
    }

    response = await handle_slack_interaction(slack_payload)

    assert response.get("replace_original") is True
    assert "Rejected by @sarah_growth" in response.get("text", "")

    # Verify DB action was flipped to rejected
    async with async_session_factory() as session:
        refreshed = await session.get(ApprovalAction, action_id)
        assert refreshed.status == "rejected"
        assert refreshed.reviewed_by == "slack:@sarah_growth"
        assert refreshed.rejection_reason == "Rejected via Slack"


@pytest.mark.asyncio
async def test_handle_slack_interaction_already_decided():
    action_id = "test_slack_act_already_done"
    async with async_session_factory() as session:
        action = ApprovalAction(
            id=action_id,
            run_id="run_slack_3",
            agent="FraudAgent",
            action_type="fraud_hold",
            status="executed",
            reviewed_by="admin",
            payload={},
        )
        session.add(action)
        await session.commit()

    slack_payload = {
        "user": {"username": "late_user"},
        "actions": [{"action_id": "hitl_approve_action", "value": action_id}],
    }

    response = await handle_slack_interaction(slack_payload)
    assert response.get("response_type") == "ephemeral"
    assert "already `executed`" in response.get("text", "")


# ── 5. FastAPI Endpoints Integration Tests ───────────────────────────


def test_api_slack_interactions_endpoint(test_client):
    action_id = "api_test_act_1"
    now = int(time.time())
    secret = "test_signing_secret_123"

    payload_json = {
        "user": {"username": "alex_ops"},
        "actions": [{"action_id": "hitl_approve_action", "value": action_id}],
    }
    encoded_payload = f"payload={json.dumps(payload_json)}"
    raw_body = encoded_payload.encode("utf-8")
    sig = _generate_slack_signature(raw_body, now, secret)

    with patch("ecommerce_ops.infra.slack_interactive.app_settings.SLACK_SIGNING_SECRET", secret), \
         patch("ecommerce_ops.api.slack.handle_slack_interaction", new_callable=AsyncMock) as mock_handle:

        mock_handle.return_value = {
            "replace_original": True,
            "text": "✅ Approved by @alex_ops",
        }

        resp = test_client.post(
            "/api/v1/slack/interactions",
            content=raw_body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Slack-Request-Timestamp": str(now),
                "X-Slack-Signature": sig,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("replace_original") is True
        assert "Approved by @alex_ops" in data.get("text")


def test_api_slack_command_pending(test_client):
    now = int(time.time())
    secret = "test_signing_secret_123"
    form_data = "command=%2Fopsiq&text=pending&user_name=alex"
    raw_body = form_data.encode("utf-8")
    sig = _generate_slack_signature(raw_body, now, secret)

    with patch("ecommerce_ops.infra.slack_interactive.app_settings.SLACK_SIGNING_SECRET", secret):
        resp = test_client.post(
            "/api/v1/slack/command",
            content=raw_body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Slack-Request-Timestamp": str(now),
                "X-Slack-Signature": sig,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "response_type" in data
