import logging

from ecommerce_ops.api.ws import ws_manager
from ecommerce_ops.config import settings
from ecommerce_ops.infra.email import notify_email
from ecommerce_ops.infra.outbound_webhooks import dispatch_outbound_webhook

logger = logging.getLogger("ecommerce_ops.infra.notifications")


async def notify_hitl_request(
    agent: str,
    action_id: str,
    action_type: str,
    risk_level: str,
    confidence: float,
):
    msg = (
        f"[HITL] {agent} — {action_type} (risk: {risk_level}, conf: {confidence:.2f})\n"
        f"Action ID: {action_id}"
    )
    logger.info("NOTIFY: %s", msg)
    await _send_slack(msg)
    await notify_email("HITL approval required", msg)
    await dispatch_outbound_webhook("hitl_request", {"agent": agent, "action_id": action_id})
    await ws_manager.broadcast(
        {
            "type": "notification",
            "payload": {
                "kind": "hitl_request",
                "agent": agent,
                "action_id": action_id,
                "action_type": action_type,
                "risk_level": risk_level,
                "confidence": confidence,
                "message": msg,
            },
        }
    )


async def notify_pipeline_failed(
    run_id: str,
    error: str,
):
    msg = f"[FAIL] Pipeline {run_id} failed: {error}"
    logger.error("NOTIFY: %s", msg)
    await _send_slack(msg)
    await notify_email("Pipeline failure", msg)
    await dispatch_outbound_webhook("pipeline_failed", {"run_id": run_id, "error": error})
    await ws_manager.broadcast(
        {
            "type": "notification",
            "payload": {
                "kind": "pipeline_failed",
                "run_id": run_id,
                "error": error,
                "message": msg,
            },
        }
    )


async def notify_agent_graduated(
    agent: str,
    new_level: str,
    streak: int,
):
    msg = f"[GRADUATE] {agent} promoted to {new_level} (streak: {streak})"
    logger.info("NOTIFY: %s", msg)
    await _send_slack(msg)
    await notify_email("Agent graduated", msg)
    await dispatch_outbound_webhook(
        "agent_graduated", {"agent": agent, "new_level": new_level, "streak": streak}
    )
    await ws_manager.broadcast(
        {
            "type": "notification",
            "payload": {
                "kind": "agent_graduated",
                "agent": agent,
                "new_level": new_level,
                "streak": streak,
                "message": msg,
            },
        }
    )


async def notify_execution_failed(
    action_id: str,
    action_type: str,
    agent: str,
    error: str,
    context: str = "auto-execution",
):
    """Alert operators when a live shop action fails after approval."""
    msg = (
        f"[EXEC-FAIL] {agent} — {action_type} ({context}) failed\n"
        f"Action ID: {action_id}\nReason: {error}"
    )
    logger.error("NOTIFY: %s", msg)
    await _send_slack(msg)
    await notify_email("Shop action failed", msg)
    await dispatch_outbound_webhook(
        "execution_failed",
        {"action_id": action_id, "action_type": action_type, "agent": agent, "error": error},
    )
    await ws_manager.broadcast(
        {
            "type": "notification",
            "payload": {
                "kind": "execution_failed",
                "action_id": action_id,
                "action_type": action_type,
                "agent": agent,
                "error": error,
                "context": context,
                "message": msg,
            },
        }
    )


async def notify_daily_summary(stats: dict):
    msg = (
        f"[DAILY] Pipeline runs: {stats.get('runs', 0)}, "
        f"decisions: {stats.get('decisions', 0)}, "
        f"pending HITL: {stats.get('pending_hitl', 0)}"
    )
    logger.info("NOTIFY: %s", msg)
    await _send_slack(msg)
    await notify_email("Daily ops summary", msg)
    await dispatch_outbound_webhook("daily_summary", stats)


async def _send_slack(message: str):
    """Send to Slack via an incoming-webhook URL, or the bot token as fallback."""
    if settings.SLACK_WEBHOOK_URL:
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    settings.SLACK_WEBHOOK_URL,
                    json={"text": message},
                    headers={"Content-Type": "application/json"},
                )
            if resp.status_code >= 300:
                logger.warning("Slack webhook returned status %s", resp.status_code)
        except Exception as e:
            logger.warning("Slack webhook notification failed: %s", e)
        return

    if not settings.SLACK_BOT_TOKEN:
        return
    try:
        token = settings.SLACK_BOT_TOKEN.get_secret_value()
        channel = settings.SLACK_CHANNEL or "#general"
        import httpx

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"channel": channel, "text": message},
            )
        if resp.status_code >= 300:
            logger.warning("Slack bot API returned status %s", resp.status_code)
    except Exception as e:
        logger.warning("Slack notification failed: %s", e)
