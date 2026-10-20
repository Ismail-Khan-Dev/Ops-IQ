"""
Slack Interactive HITL Bot Module
Provides Slack Block Kit message generation, HMAC signature verification,
interactive approval/rejection button dispatch, and in-place response updates.
"""

import hashlib
import hmac
import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx
from sqlalchemy import select

from ecommerce_ops.api.metrics import (
    METRIC_AGENT_CONFIDENCE_AVG,
    METRIC_AGENT_EXECUTION_ERRORS,
    METRIC_DECISIONS_APPROVED,
    METRIC_DECISIONS_REJECTED,
)
from ecommerce_ops.api.ws import ws_manager
from ecommerce_ops.config import Environment
from ecommerce_ops.config import settings as app_settings
from ecommerce_ops.infra.notifications import notify_execution_failed
from ecommerce_ops.models import ApprovalAction, AuditEntry, async_session_factory
from ecommerce_ops.pipeline.runner import execute_shop_action, update_agent_streak
from ecommerce_ops.utils import utc_now

logger = logging.getLogger("ecommerce_ops.infra.slack_interactive")

AGENT_EMOJI_MAP = {
    "FraudAgent": "🛡️",
    "fraud": "🛡️",
    "InventoryAgent": "📦",
    "inventory": "📦",
    "PricingAgent": "🏷️",
    "pricing": "🏷️",
    "PriceOptimizationAgent": "🏷️",
    "ReviewsAgent": "⭐",
    "reviews": "⭐",
    "MarketingAgent": "📢",
    "marketing": "📢",
    "OrderSwapsAgent": "🔄",
    "SmartReturnsAgent": "🔁",
    "AbandonedCartAgent": "🛒",
    "cart_recovery": "🛒",
    "CustomerSupportAgent": "💬",
    "customer_support": "💬",
}

RISK_BADGE_MAP = {
    "critical": "🔴 CRITICAL",
    "high": "🟠 HIGH",
    "medium": "🟡 MEDIUM",
    "low": "🟢 LOW",
}


def verify_slack_signature(
    raw_body: bytes,
    timestamp: Optional[str],
    signature: Optional[str],
    signing_secret: Optional[str] = None,
) -> bool:
    """Verify incoming request from Slack using HMAC-SHA256 signature.

    Complies with Slack standard:
    sig_basestring = 'v0:' + timestamp + ':' + body
    my_signature = 'v0=' + hmac_sha256(signing_secret, sig_basestring)
    """
    if not signing_secret:
        if app_settings.SLACK_SIGNING_SECRET:
            signing_secret = app_settings.SLACK_SIGNING_SECRET.get_secret_value()
        elif app_settings.ENV != Environment.PRODUCTION:
            logger.warning("SLACK_SIGNING_SECRET not set; skipping signature verification in dev")
            return True
        else:
            logger.error("SLACK_SIGNING_SECRET required in production")
            return False

    if not timestamp or not signature:
        logger.warning("Missing Slack timestamp or signature header")
        return False

    # Prevent replay attacks: timestamp must be within 5 minutes
    try:
        ts = int(timestamp)
        now = int(time.time())
        if abs(now - ts) > 300:
            logger.warning("Slack timestamp drift > 300s (ts=%d, now=%d)", ts, now)
            return False
    except (ValueError, TypeError):
        return False

    sig_basestring = f"v0:{timestamp}:{raw_body.decode('utf-8', errors='replace')}".encode("utf-8")
    computed_hash = hmac.new(
        signing_secret.encode("utf-8"), sig_basestring, hashlib.sha256
    ).hexdigest()
    expected_sig = f"v0={computed_hash}"

    return hmac.compare_digest(expected_sig, signature)


def build_hitl_approval_blocks(
    action_id: str,
    agent: str,
    action_type: str,
    risk_level: str,
    confidence: float,
    payload: Optional[Dict[str, Any]] = None,
    impact: Optional[Dict[str, Any]] = None,
    dashboard_url: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Build rich Slack Block Kit layout with interactive Approve/Reject buttons."""
    payload = payload or {}
    impact = impact or {}

    emoji = AGENT_EMOJI_MAP.get(agent, "🤖")
    risk_badge = RISK_BADGE_MAP.get(risk_level.lower(), risk_level.upper())
    financial_impact = impact.get("financial_impact", 0.0)
    impact_str = f"${financial_impact:,.2f}" if financial_impact else "N/A"

    # Contextual evidence summary
    details_lines = []
    if "order_id" in payload:
        details_lines.append(f"• *Order ID:* `{payload['order_id']}`")
    if "order_total" in payload and payload["order_total"]:
        details_lines.append(f"• *Total Value:* `${float(payload['order_total']):,.2f}`")
    if "risk_signals" in payload and payload["risk_signals"]:
        signals = payload["risk_signals"]
        if isinstance(signals, list):
            signals = ", ".join(signals)
        details_lines.append(f"• *Risk Factors:* {signals}")
    if "fraud_score" in payload and payload["fraud_score"] is not None:
        details_lines.append(f"• *Fraud Score:* `{payload['fraud_score']}/100`")
    if "sku" in payload:
        details_lines.append(f"• *SKU:* `{payload['sku']}`")
    if "proposed_price" in payload:
        details_lines.append(f"• *Proposed Price:* `${payload['proposed_price']}`")
    if "reorder_quantity" in payload:
        details_lines.append(f"• *Reorder Qty:* `{payload['reorder_quantity']}`")
    if "customer_email" in payload and payload["customer_email"]:
        details_lines.append(f"• *Customer:* `{payload['customer_email']}`")
    if "reason_notes" in payload:
        details_lines.append(f"• *Notes:* {payload['reason_notes']}")

    details_text = "\n".join(details_lines) if details_lines else "• Automated policy threshold evaluation"

    blocks: List[Dict[str, Any]] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{emoji} OpsIQ: Human-In-The-Loop Approval Required",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Agent:*\n{agent}"},
                {"type": "mrkdwn", "text": f"*Action:*\n`{action_type}`"},
                {"type": "mrkdwn", "text": f"*Risk Level:*\n{risk_badge}"},
                {"type": "mrkdwn", "text": f"*Confidence:*\n{confidence:.0%}"},
                {"type": "mrkdwn", "text": f"*Financial Impact:*\n{impact_str}"},
                {"type": "mrkdwn", "text": f"*Action ID:*\n`{action_id}`"},
            ],
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Details & Evidence:*\n{details_text}",
            },
        },
        {"type": "divider"},
        {
            "type": "actions",
            "block_id": f"hitl_actions_{action_id}",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "✅ Approve", "emoji": True},
                    "style": "primary",
                    "action_id": "hitl_approve_action",
                    "value": action_id,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "❌ Reject", "emoji": True},
                    "style": "danger",
                    "action_id": "hitl_reject_action",
                    "value": action_id,
                },
            ],
        },
    ]

    # Add dashboard link button if dashboard URL provided
    if dashboard_url:
        blocks[-1]["elements"].append(
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "🔍 Review in Dashboard", "emoji": True},
                "action_id": "view_dashboard",
                "url": f"{dashboard_url}/approvals?id={action_id}",
            }
        )

    # Context footer with timestamp
    blocks.append(
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"OpsIQ Autonomous Pipeline • Generated at <!date^{int(time.time())}^{{time_secs}}|{utc_now().isoformat()}>",
                }
            ],
        }
    )

    return blocks


def build_resolved_slack_blocks(
    action_id: str,
    agent: str,
    action_type: str,
    status: str,
    operator: str,
    exec_msg: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Build updated Block Kit message once an action has been decided."""
    is_approved = status in ("executed", "approved")
    badge = "✅ *APPROVED*" if is_approved else "❌ *REJECTED*"
    operator_clean = operator.replace("slack:@", "@")

    status_line = (
        f"{badge} by *{operator_clean}* at {utc_now().strftime('%Y-%m-%d %H:%M:%S UTC')}"
    )
    if exec_msg:
        status_line += f"\n• Result: `{exec_msg}`"

    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "OpsIQ Approval Resolved",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Action ID:*\n`{action_id}`"},
                {"type": "mrkdwn", "text": f"*Agent:*\n{agent}"},
                {"type": "mrkdwn", "text": f"*Action Type:*\n`{action_type}`"},
                {"type": "mrkdwn", "text": f"*Status:*\n`{status.upper()}`"},
            ],
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": status_line,
            },
        },
    ]


async def send_interactive_hitl_notification(
    action_id: str,
    agent: str,
    action_type: str,
    risk_level: str,
    confidence: float,
    payload: Optional[Dict[str, Any]] = None,
    impact: Optional[Dict[str, Any]] = None,
    dashboard_url: Optional[str] = None,
) -> bool:
    """Send interactive HITL notification to Slack with Action buttons."""
    blocks = build_hitl_approval_blocks(
        action_id=action_id,
        agent=agent,
        action_type=action_type,
        risk_level=risk_level,
        confidence=confidence,
        payload=payload,
        impact=impact,
        dashboard_url=dashboard_url,
    )
    fallback_text = (
        f"[HITL Approval Required] {agent} - {action_type} (risk: {risk_level}, conf: {confidence:.0%}) "
        f"Action ID: {action_id}"
    )

    # 1. Preferred: Slack incoming webhook URL
    if app_settings.SLACK_WEBHOOK_URL:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    app_settings.SLACK_WEBHOOK_URL,
                    json={"text": fallback_text, "blocks": blocks},
                    headers={"Content-Type": "application/json"},
                )
            if resp.status_code < 300:
                logger.info("Sent interactive Slack HITL alert via webhook for %s", action_id)
                return True
            logger.warning("Slack webhook returned %d for %s", resp.status_code, action_id)
        except Exception as e:
            logger.warning("Failed sending Slack interactive webhook: %s", e)

    # 2. Slack Bot Token chat.postMessage
    if app_settings.SLACK_BOT_TOKEN:
        try:
            token = app_settings.SLACK_BOT_TOKEN.get_secret_value()
            channel = app_settings.SLACK_CHANNEL or "#general"
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    json={"channel": channel, "text": fallback_text, "blocks": blocks},
                )
            if resp.status_code < 300 and resp.json().get("ok"):
                logger.info("Sent interactive Slack HITL alert via Bot API for %s", action_id)
                return True
            logger.warning("Slack Bot API returned error for %s: %s", action_id, resp.text)
        except Exception as e:
            logger.warning("Failed sending Slack Bot API alert: %s", e)

    return False


async def handle_slack_interaction(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Process an interactive action clicked from Slack (Approve or Reject).

    Returns a response dictionary that Slack uses to replace the message in-place.
    """
    user_info = payload.get("user") or {}
    username = user_info.get("username") or user_info.get("name") or user_info.get("id") or "slack_user"
    operator = f"slack:@{username}"

    actions = payload.get("actions", [])
    if not actions:
        return {"response_type": "ephemeral", "text": "No action found in payload"}

    clicked_action = actions[0]
    action_button_id = clicked_action.get("action_id")
    action_id = clicked_action.get("value")

    if not action_id:
        return {"response_type": "ephemeral", "text": "Missing action ID in button"}

    async with async_session_factory() as db:
        res = await db.execute(
            select(ApprovalAction).where(ApprovalAction.id == action_id).with_for_update()
        )
        action = res.scalar_one_or_none()

        if not action:
            return {
                "response_type": "ephemeral",
                "text": f"⚠️ Action `{action_id}` not found in database.",
            }

        if action.status != "pending":
            return {
                "response_type": "ephemeral",
                "text": f"⚠️ Action `{action_id}` is already `{action.status}` (decided by {action.reviewed_by or 'system'}).",
            }

        # ── Approve ─────────────────────────────────────────
        if action_button_id == "hitl_approve_action":
            action.reviewed_by = operator
            action.reviewed_at = utc_now()
            action.operator_notes = f"Approved via Slack by @{username}"
            action.status = "approved"

            financial_impact = (action.impact or {}).get("financial_impact", 0.0)
            audit_entry = AuditEntry(
                action_id=action.id,
                timestamp=utc_now(),
                agent=action.agent,
                action_type=action.action_type,
                decision="approved",
                operator=operator,
                confidence_score=action.confidence_score,
                financial_impact=financial_impact,
                details={
                    "notes": action.operator_notes,
                    "execution_status": "approved",
                    "channel": "slack",
                },
            )
            db.add(audit_entry)
            await db.commit()

            # Execute shop action
            action.status = "executing"
            try:
                success, exec_msg = await execute_shop_action(action)
            except Exception as exc:
                success = False
                exec_msg = f"execution_error: {exc}"

            action.status = "executed" if success else "failed"
            if not success:
                action.operator_notes = f"{action.operator_notes} [Error: {exec_msg}]".strip()
                METRIC_AGENT_EXECUTION_ERRORS.labels(agent=action.agent).inc()
                await notify_execution_failed(
                    action_id=action.id,
                    action_type=action.action_type,
                    agent=action.agent,
                    error=exec_msg,
                    context="slack-approval",
                )

            audit_entry.details["execution_status"] = action.status
            audit_entry.details["execution_message"] = exec_msg if not success else None

            await update_agent_streak(action.agent, success, action.confidence_score, db)
            await db.commit()

            # Broadcast WebSocket updates
            await ws_manager.broadcast(
                {
                    "type": "action_updated",
                    "payload": {"id": action.id, "status": action.status, "agent": action.agent},
                }
            )

            METRIC_DECISIONS_APPROVED.labels(agent=action.agent).inc()
            METRIC_AGENT_CONFIDENCE_AVG.labels(agent=action.agent).set(action.confidence_score)

            resolved_blocks = build_resolved_slack_blocks(
                action_id=action.id,
                agent=action.agent,
                action_type=action.action_type,
                status=action.status,
                operator=operator,
                exec_msg=exec_msg if success else f"Execution failed: {exec_msg}",
            )
            return {
                "replace_original": True,
                "text": f"✅ Approved by @{username} • Status: {action.status}",
                "blocks": resolved_blocks,
            }

        # ── Reject ──────────────────────────────────────────
        elif action_button_id == "hitl_reject_action":
            action.reviewed_by = operator
            action.reviewed_at = utc_now()
            action.rejection_reason = "Rejected via Slack"
            action.operator_notes = f"Rejected via Slack by @{username}"
            action.status = "rejected"

            financial_impact = (action.impact or {}).get("financial_impact", 0.0)
            audit_entry = AuditEntry(
                action_id=action.id,
                timestamp=utc_now(),
                agent=action.agent,
                action_type=action.action_type,
                decision="rejected",
                operator=operator,
                confidence_score=action.confidence_score,
                financial_impact=financial_impact,
                details={
                    "reason": action.rejection_reason,
                    "notes": action.operator_notes,
                    "channel": "slack",
                },
            )
            db.add(audit_entry)
            await update_agent_streak(action.agent, False, action.confidence_score, db)
            await db.commit()

            await ws_manager.broadcast(
                {
                    "type": "action_updated",
                    "payload": {"id": action.id, "status": "rejected", "agent": action.agent},
                }
            )

            METRIC_DECISIONS_REJECTED.labels(agent=action.agent).inc()
            METRIC_AGENT_CONFIDENCE_AVG.labels(agent=action.agent).set(action.confidence_score)

            resolved_blocks = build_resolved_slack_blocks(
                action_id=action.id,
                agent=action.agent,
                action_type=action.action_type,
                status="rejected",
                operator=operator,
                exec_msg="Action rejected by operator via Slack",
            )
            return {
                "replace_original": True,
                "text": f"❌ Rejected by @{username}",
                "blocks": resolved_blocks,
            }

        return {"response_type": "ephemeral", "text": f"Unknown action: {action_button_id}"}
