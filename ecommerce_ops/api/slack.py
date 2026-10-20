"""
Slack Interactive API Endpoints
Handles incoming Slack interaction payloads (Approve/Reject button clicks),
slash commands, and notification testing.
"""

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import func, select

from ecommerce_ops.infra.slack_interactive import (
    handle_slack_interaction,
    send_interactive_hitl_notification,
    verify_slack_signature,
)
from ecommerce_ops.models import ApprovalAction, async_session_factory
from ecommerce_ops.security.auth import require_admin
from ecommerce_ops.security.models import User

logger = logging.getLogger("ecommerce_ops.api.slack")

router = APIRouter(prefix="/slack", tags=["slack"])


@router.post("/interactions")
async def slack_interactions(
    request: Request,
    x_slack_request_timestamp: Optional[str] = Header(None, alias="X-Slack-Request-Timestamp"),
    x_slack_signature: Optional[str] = Header(None, alias="X-Slack-Signature"),
):
    """Handle interactive callbacks when an operator clicks Approve/Reject in Slack."""
    raw_body = await request.body()

    # 1. Verify HMAC signature
    is_valid = verify_slack_signature(
        raw_body=raw_body,
        timestamp=x_slack_request_timestamp,
        signature=x_slack_signature,
    )
    if not is_valid:
        logger.warning("Rejected Slack interaction: invalid signature")
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    # 2. Parse form-encoded payload
    form_data = await request.form()
    payload_str = form_data.get("payload")
    if not payload_str:
        # Fallback to direct JSON body if sent as json
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception:
            raise HTTPException(status_code=400, detail="Missing interaction payload")
    else:
        try:
            payload = json.loads(payload_str)
        except Exception as e:
            logger.error("Failed to parse Slack interaction payload: %s", e)
            raise HTTPException(status_code=400, detail="Malformed JSON in payload")

    # 3. Process interaction (Approve / Reject)
    response_blocks = await handle_slack_interaction(payload)
    return response_blocks


@router.post("/command")
async def slack_slash_command(
    request: Request,
    command: str = Form(...),
    text: Optional[str] = Form(""),
    user_name: Optional[str] = Form("operator"),
    x_slack_request_timestamp: Optional[str] = Header(None, alias="X-Slack-Request-Timestamp"),
    x_slack_signature: Optional[str] = Header(None, alias="X-Slack-Signature"),
):
    """Handle /opsiq slash commands from Slack (e.g. /opsiq pending)."""
    raw_body = await request.body()
    is_valid = verify_slack_signature(
        raw_body=raw_body,
        timestamp=x_slack_request_timestamp,
        signature=x_slack_signature,
    )
    if not is_valid:
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    subcmd = (text or "").strip().lower()

    if subcmd in ("pending", "approvals", "queue"):
        async with async_session_factory() as session:
            res = await session.execute(
                select(ApprovalAction)
                .where(ApprovalAction.status == "pending")
                .order_by(ApprovalAction.created_at.desc())
                .limit(5)
            )
            pending_actions = res.scalars().all()

        if not pending_actions:
            return {
                "response_type": "ephemeral",
                "text": "🎉 All clear! There are currently no pending approvals in OpsIQ.",
            }

        lines = [f"📋 *OpsIQ Pending Approvals ({len(pending_actions)} most recent):*"]
        for act in pending_actions:
            lines.append(
                f"• `{act.id}` | *{act.agent}* | `{act.action_type}` | Risk: *{act.risk_level.upper()}* | Conf: *{act.confidence_score:.0%}*"
            )
        lines.append("\n_Click the Approve or Reject buttons in the alert cards above to decide._")

        return {
            "response_type": "ephemeral",
            "text": "\n".join(lines),
        }

    # Default help / status
    async with async_session_factory() as session:
        count_res = await session.execute(
            select(func.count(ApprovalAction.id)).where(ApprovalAction.status == "pending")
        )
        pending_count = count_res.scalar() or 0

    return {
        "response_type": "ephemeral",
        "text": (
            f"🤖 *OpsIQ Multi-Agent Operations Bot*\n"
            f"• Pending Approvals: *{pending_count}*\n"
            f"• Commands: `/opsiq pending` (list queue), `/opsiq status`"
        ),
    }


class TestNotificationRequest(BaseModel):
    agent: str = "FraudAgent"
    action_type: str = "fraud_hold"
    risk_level: str = "high"
    confidence: float = 0.95
    order_id: str = "ORD-TEST-999"
    order_total: float = 1250.00
    risk_signals: list = ["high_order_value_over_1000", "billing_shipping_postal_mismatch"]


@router.post("/test-notification")
async def send_test_slack_notification(
    req: TestNotificationRequest = TestNotificationRequest(),
    _: User = Depends(require_admin),
):
    """Admin endpoint to test sending an interactive HITL approval card to Slack."""
    success = await send_interactive_hitl_notification(
        action_id=f"test_{req.order_id}",
        agent=req.agent,
        action_type=req.action_type,
        risk_level=req.risk_level,
        confidence=req.confidence,
        payload={
            "order_id": req.order_id,
            "order_total": req.order_total,
            "risk_signals": req.risk_signals,
            "fraud_score": 85,
        },
        impact={"financial_impact": req.order_total},
    )
    return {
        "sent": success,
        "message": "Dispatched interactive HITL card to Slack" if success else "Slack webhook/token not configured",
    }
