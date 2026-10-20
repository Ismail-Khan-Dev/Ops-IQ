import functools
import logging
import math
import uuid
from datetime import timedelta
from typing import Any, Dict, Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ecommerce_ops.api.metrics import (
    METRIC_AGENT_EXECUTION_ERRORS,
    METRIC_DECISIONS_AUTO_APPROVED,
    METRIC_DECISIONS_CREATED,
    METRIC_FINANCIAL_IMPACT,
    METRIC_PIPELINE_RUNS,
    METRIC_SHOP_EXECUTION_DURATION,
    METRIC_SHOP_EXECUTIONS,
)
from ecommerce_ops.api.ws import ws_manager
from ecommerce_ops.config import Environment
from ecommerce_ops.config import settings as app_settings
from ecommerce_ops.graph.supervisor import Supervisor
from ecommerce_ops.infra.async_utils import LoopAwareLock
from ecommerce_ops.infra.notifications import (
    notify_agent_graduated,
    notify_execution_failed,
    notify_hitl_request,
    notify_pipeline_failed,
)
from ecommerce_ops.models import (
    AgentStatus,
    ApprovalAction,
    AuditEntry,
    OutboxMessage,
    PipelineRun,
    StoreSettings,
    async_session_factory,
)
from ecommerce_ops.observability.ab_testing import run_ab_experiment
from ecommerce_ops.observability.evaluation import evaluation_framework
from ecommerce_ops.observability.langfuse_client import langfuse_client
from ecommerce_ops.pipeline.builder import build_payload_and_evidence
from ecommerce_ops.safety.safety_rules import evaluate_action_safety
from ecommerce_ops.utils import utc_now

# ── Locked batch guard ─────────────────────────────────────────
# In-process asyncio lock per run_id (prevents concurrent runs in same process).
# For multi-worker deployments, add a Redis/distributed lock via backend.
# LoopAwareLock: these locks live in a module-level dict and are reused across
# event loops (uvicorn --reload, per-test loops), so a plain asyncio.Lock would
# bind to the first loop it contends on and break the next one.
_pipeline_locks: dict[str, LoopAwareLock] = {}
_pipeline_lock_times: dict[str, float] = {}
_LOCK_TTL_SECONDS = 3600  # clean up locks older than 1 hour


def _get_pipeline_lock(run_id: str) -> LoopAwareLock:
    """Get or create a lock for the given run_id, with TTL cleanup."""
    import time as _time

    now = _time.monotonic()
    # Evict expired locks
    expired = [k for k, t in _pipeline_lock_times.items() if now - t > _LOCK_TTL_SECONDS]
    for k in expired:
        _pipeline_locks.pop(k, None)
        _pipeline_lock_times.pop(k, None)

    if run_id not in _pipeline_locks:
        _pipeline_locks[run_id] = LoopAwareLock()
    _pipeline_lock_times[run_id] = now
    return _pipeline_locks[run_id]


async def _try_register_pipeline_run(
    run_id: str,
    session: AsyncSession,
    shop_domain: Optional[str] = None,
) -> PipelineRun | None:
    """Attempt to register a pipeline run idempotently.

    Uses ``INSERT … ON CONFLICT DO NOTHING`` against the ``pipeline_runs``
    table.  Returns the new ``PipelineRun`` row if this call owns the run,
    or ``None`` if the ``run_id`` was already registered (another worker or
    a prior invocation beat us).
    """
    try:
        from ecommerce_ops.models.db import is_sqlite

        if is_sqlite:
            from sqlalchemy.dialects.sqlite import insert as dialect_insert
        else:
            from sqlalchemy.dialects.postgresql import insert as dialect_insert

        stmt = (
            dialect_insert(PipelineRun)
            .values(run_id=run_id, status="running", shop_domain=shop_domain, started_at=utc_now())
            .on_conflict_do_nothing(index_elements=[PipelineRun.run_id])
        )
        result = await session.execute(stmt)
        if result.rowcount == 0:
            return None
        # Fetch the row we just inserted to get the ORM object
        row = await session.execute(select(PipelineRun).where(PipelineRun.run_id == run_id))
        return row.scalar_one()
    except Exception:
        return None


logger = logging.getLogger("ecommerce_ops.pipeline.runner")


async def _resolve_shop_credentials(
    shop_domain: Optional[str] = None,
) -> tuple[str | None, str | None]:
    """Resolve Shopify credentials for a shop.

    When ``shop_domain`` is given, the OAuth-installed credential for that
    store (``shopify_shop_credentials``) is used — this powers multi-store
    runs.  Otherwise the env-configured default store is used.  Returns
    ``(shop_domain, access_token)`` or ``(None, None)`` when unavailable.
    """
    if shop_domain:
        from ecommerce_ops.models.db import ShopifyShopCredential, async_session_factory

        try:
            async with async_session_factory() as session:
                res = await session.execute(
                    select(ShopifyShopCredential).where(
                        ShopifyShopCredential.shop_domain == shop_domain,
                        ShopifyShopCredential.is_active.is_(True),
                    )
                )
                cred = res.scalar_one_or_none()
        except Exception:
            logger.warning("Failed to load shop credentials for %s", shop_domain, exc_info=True)
            return None, None
        if cred is None:
            return None, None
        return cred.shop_domain, cred.access_token

    shop_domain = app_settings.SHOPIFY_SHOP_DOMAIN
    access_token_raw = app_settings.SHOPIFY_ACCESS_TOKEN
    access_token = access_token_raw.get_secret_value() if access_token_raw else None
    if not shop_domain or not access_token:
        return None, None
    return shop_domain, access_token


async def fetch_shopify_data(
    shop_domain: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Fetch real data from Shopify if credentials are configured."""
    from ecommerce_ops.connectors.shopify.client import ShopifyClient

    shop_domain, access_token = await _resolve_shop_credentials(shop_domain)

    if not shop_domain or not access_token:
        logger.debug("Shopify credentials not configured, using mock data")
        return None

    try:
        client = ShopifyClient(
            shop_domain=shop_domain,
            access_token=access_token,
            api_version=app_settings.SHOPIFY_API_VERSION,
        )

        # Fetch inventory
        inventory_response = await client.get_products(limit=100)
        inventory_data = []
        for product in inventory_response.get("products", []):
            for variant in product.get("variants", []):
                inventory_data.append(
                    {
                        "sku": variant.get("sku", f"SKU-{variant['id']}"),
                        "stock": variant.get("inventory_quantity", 0),
                        "price": float(variant.get("price", 0)),
                        "variant_id": str(variant["id"]),
                    }
                )

        # Fetch recent orders (last 24h)
        orders_response = await client.get_orders(
            status="any",
            limit=50,
            created_at_min=(utc_now() - timedelta(hours=24)).isoformat(),
        )
        active_orders = []
        for order in orders_response.get("orders", []):
            if order.get("fulfillment_status") != "fulfilled":
                active_orders.append(
                    {
                        "id": str(order["id"]),
                        "line_items": [
                            {"sku": item.get("sku", ""), "quantity": item.get("quantity", 1)}
                            for item in order.get("line_items", [])
                        ],
                        "order_total": float(order.get("total_price", 0)),
                    }
                )

        # Fetch reviews (from order notes/comments - placeholder)
        reviews_data = []  # Reviews API not available in basic scope

        # Fetch abandoned carts (checkouts)
        checkouts_response = await client.get_checkouts(limit=50)
        abandoned_carts = []
        for checkout in checkouts_response.get("checkouts", []):
            # Check if checkout is abandoned (no completed order)
            if checkout.get("order") is None:
                items = []
                for item in checkout.get("line_items", []):
                    items.append(
                        {
                            "product_id": item.get("product_id", 0),
                            "variant_id": item.get("variant_id", 0),
                            "title": item.get("title", "Unknown"),
                            "sku": item.get("sku"),
                            "quantity": item.get("quantity", 1),
                            "price": float(item.get("price", 0)),
                            "total": float(item.get("line_price", 0)),
                        }
                    )

                abandoned_carts.append(
                    {
                        "id": str(checkout.get("id", f"cart-{len(abandoned_carts)}")),
                        "shop_domain": shop_domain,
                        "checkout_token": checkout.get("token"),
                        "items": items,
                        "total_value": float(checkout.get("total_price", 0)),
                        "currency": checkout.get("currency", "USD"),
                        "items_count": len(items),
                        "status": "abandoned",
                        "checkout_url": checkout.get("abandoned_checkout_url"),
                        "created_at": checkout.get("created_at"),
                        "abandoned_at": checkout.get("updated_at"),
                        "customer": {
                            "email": checkout.get("email"),
                            "first_name": checkout.get("billing_address", {}).get("first_name"),
                            "last_name": checkout.get("billing_address", {}).get("last_name"),
                        }
                        if checkout.get("email")
                        else None,
                    }
                )

        await client.close()

        return {
            "inventory_data": inventory_data,
            "active_orders": active_orders,
            "reviews_data": reviews_data,
            "abandoned_carts": abandoned_carts,
        }

    except Exception as e:
        logger.error("Failed to fetch Shopify data: %s", e)
        return None


DECISION_TYPE_MAP = {
    "HOLD_ORDER": "fraud_hold",
    "RELEASE_HOLD": "release_fraud_hold",
    "RELEASE_ORDER_HOLD": "release_fraud_hold",
    "DRAFT_PO": "purchase_order",
    "UPDATE_PRICE": "price_change",
    "POST_REVIEW_RESPONSE": "review_response",
    "DRAFT_MARKETING_CAMPAIGN": "marketing_campaign",
    "SWAP_ITEM": "order_swap",
    "FLAG_RETURN_RISK": "return_risk_flag",
    "recover_cart": "cart_recovery",
    "RECOVER_CART": "cart_recovery",
    "respond_to_ticket": "support_response",
    "RESPOND_TO_TICKET": "support_response",
}

# Capability binding for live mutations (M7): only the agent(s) authorized for
# an action type may execute it against Shopify. This is the last line of
# defense against a misbehaving or compromised agent issuing an action of a
# type it has no permission to perform. LLM agents use the snake_case keys
# from the tool-permission matrix; rule-based agents use their PascalCase
# names. The check is enforced in execute_shop_action before any live call.
ACTION_TYPE_AGENT_ALLOWLIST: dict[str, set[str]] = {
    "fraud_hold": {"FraudAgent", "fraud_detection", "fraud", "manual_operator", "system"},
    "release_fraud_hold": {"FraudAgent", "fraud_detection", "fraud", "manual_operator", "system"},
    "purchase_order": {"InventoryAgent", "inventory_management", "inventory"},
    "price_change": {
        "PricingAgent",
        "PriceOptimizationAgent",
        "price_optimization",
        "DynamicPricingAgent",
        "dynamic_pricing",
        "pricing",
    },
    "review_response": {"ReviewsAgent", "review_moderation", "reviews"},
    "marketing_campaign": {"MarketingAgent", "marketing_automation", "marketing"},
    "order_swap": {"OrderSwapsAgent", "order_swaps"},
    "return_risk_flag": {"SmartReturnsAgent", "smart_returns"},
    "cart_recovery": {"AbandonedCartAgent", "cart_recovery", "manual_operator", "system"},
    "support_response": {"CustomerSupportAgent", "customer_support", "manual_operator", "system"},
}


def _instrument_shop_execution(fn):
    """Measure duration and record the outcome of a live Shopify action.

    Decorates handlers that return ``(ok: bool, message: str)``.  The
    counter differentiates ``executed`` from ``failed`` so alerting can key
    on a rising failure rate per action type.
    """

    @functools.wraps(fn)
    async def wrapper(action: ApprovalAction, *args, **kwargs) -> tuple[bool, str]:
        import time as _t

        start = _t.monotonic()
        try:
            ok, message = await fn(action, *args, **kwargs)
            result = "executed" if ok else "failed"
            return ok, message
        except Exception:
            result = "error"
            raise
        finally:
            METRIC_SHOP_EXECUTIONS.labels(action_type=action.action_type, result=result).inc()
            METRIC_SHOP_EXECUTION_DURATION.labels(action_type=action.action_type).observe(
                _t.monotonic() - start
            )

    return wrapper


@_instrument_shop_execution
async def execute_shop_action(action: ApprovalAction) -> tuple[bool, str]:
    if action.shadow_mode:
        logger.info("[SHADOW] Simulating %s for %s", action.action_type, action.id)
        return True, "Shadow mode simulation"

    # Permission gate (M7): the initiating agent must be allowed to perform
    # this action type. Unknown action types and unlisted agents are refused
    # before any live Shopify call.
    allowed_agents = ACTION_TYPE_AGENT_ALLOWLIST.get(action.action_type)
    if allowed_agents is not None and action.agent not in allowed_agents:
        logger.warning(
            "[LIVE] Permission denied: agent %s cannot execute action_type %s (action %s)",
            action.agent,
            action.action_type,
            action.id,
        )
        return False, (
            f"agent {action.agent!r} does not have permission to execute "
            f"action_type {action.action_type!r}"
        )

    # Live execution requires Shopify credentials; without them a real action
    # cannot be performed, so report an honest failure instead of a fabricated
    # "Executed" result.
    # Multi-store (week 9): actions whose payload carries a shop_domain are
    # executed against THAT store's OAuth credentials; they never silently
    # fall back to the env store (wrong-tenant execution would be a serious
    # bug).  Without a shop_domain the env-configured store is used.
    scoped_shop = (
        action.payload.get("shop_domain") if isinstance(action.payload, dict) else None
    )
    shop_domain, access_token = await _resolve_shop_credentials(scoped_shop)
    if scoped_shop and shop_domain is None:
        logger.warning(
            "[LIVE] Cannot execute %s for %s: shop %s has no active credential",
            action.action_type,
            action.id,
            scoped_shop,
        )
        return False, (
            f"execution requires an active credential for shop {scoped_shop}"
        )
    if not shop_domain or not access_token:
        logger.warning(
            "[LIVE] Cannot execute %s for %s: Shopify not configured",
            action.action_type,
            action.id,
        )
        return False, (
            "execution requires Shopify credentials (SHOPIFY_SHOP_DOMAIN / SHOPIFY_ACCESS_TOKEN)"
        )

    from ecommerce_ops.connectors.shopify.client import ShopifyClient

    client = ShopifyClient(
        shop_domain=shop_domain,
        access_token=access_token,
        api_version=app_settings.SHOPIFY_API_VERSION,
    )
    payload = action.payload or {}
    try:
        if action.action_type == "fraud_hold":
            order_id = payload.get("order_id") or payload.get("id")
            if not order_id or not str(order_id).isdigit():
                return False, "fraud_hold requires a real Shopify order_id"

            # 1. Update order tags on Shopify for merchant visibility
            existing_tags_str = ""
            try:
                current_order = await client.get_order(str(order_id))
                existing_tags_str = current_order.get("order", {}).get("tags", "")
            except Exception as e:
                logger.warning("Could not fetch order %s tags: %s", order_id, e)

            tags_list = [t.strip() for t in existing_tags_str.split(",") if t.strip()]
            if "FRAUD_HOLD" not in tags_list:
                tags_list.append("FRAUD_HOLD")
            await client.update_order(str(order_id), {"tags": ", ".join(tags_list)})

            # 2. 3PL Interceptor: Hold fulfillment orders to prevent warehouse picking
            notes = (
                payload.get("reason_notes")
                or f"OpsIQ Fraud Interceptor: Hold placed for risk assessment (Score: {payload.get('fraud_score', 'High')})"
            )
            reason = payload.get("hold_reason") or "high_risk_of_fraud"
            held_results = await client.hold_order_fulfillments(
                str(order_id),
                reason=reason,
                reason_notes=notes,
            )
            held_count = len(held_results)
            logger.info(
                "Applied FRAUD_HOLD to order %s and intercepted %d 3PL fulfillment order(s)",
                order_id,
                held_count,
            )
            return (
                True,
                f"Applied FRAUD_HOLD to order {order_id} and intercepted {held_count} fulfillment order(s)",
            )

        if action.action_type == "release_fraud_hold":
            order_id = payload.get("order_id") or payload.get("id")
            if not order_id or not str(order_id).isdigit():
                return False, "release_fraud_hold requires a real Shopify order_id"

            # 1. Release fulfillment orders so 3PL warehouse can fulfill
            released_results = await client.release_order_fulfillments(str(order_id))
            released_count = len(released_results)

            # 2. Update tags: remove FRAUD_HOLD and tag FRAUD_CLEARED
            existing_tags_str = ""
            try:
                current_order = await client.get_order(str(order_id))
                existing_tags_str = current_order.get("order", {}).get("tags", "")
            except Exception as e:
                logger.warning("Could not fetch order %s tags: %s", order_id, e)

            tags_list = [
                t.strip()
                for t in existing_tags_str.split(",")
                if t.strip() and t.strip() != "FRAUD_HOLD"
            ]
            if "FRAUD_CLEARED" not in tags_list:
                tags_list.append("FRAUD_CLEARED")
            await client.update_order(str(order_id), {"tags": ", ".join(tags_list)})

            logger.info(
                "Released FRAUD_HOLD for order %s and unblocked %d 3PL fulfillment order(s)",
                order_id,
                released_count,
            )
            return (
                True,
                f"Released FRAUD_HOLD for order {order_id} and unblocked {released_count} fulfillment order(s)",
            )

        if action.action_type == "price_change":
            sku = payload.get("sku")
            new_price = payload.get("proposed_price", payload.get("new_price"))
            if not sku or new_price is None:
                return False, "price_change requires sku and proposed_price in payload"
            products = (await client.get_products(limit=250)).get("products", [])
            target = None
            target_sku = str(sku).strip().upper()
            for product in products:
                for variant in product.get("variants", []):
                    if str(variant.get("sku", "")).strip().upper() == target_sku:
                        target = (str(product["id"]), str(variant["id"]))
                        break
                if target:
                    break
            if not target:
                return False, f"price_change: no product variant found for sku {sku}"
            product_id, variant_id = target
            await client.update_product(
                product_id, {"variants": [{"id": variant_id, "price": str(new_price)}]}
            )
            logger.info("Updated price for variant %s to %s", variant_id, new_price)
            return True, f"Updated price for {sku} to {new_price}"

        if action.action_type == "purchase_order":
            # A supplier PO has no standard Shopify Admin API equivalent; it
            # belongs in an ERP/fulfilment system. Fail honest, never fabricate
            # a "purchased" result.
            location_id = payload.get("inventory_location_id")
            reorder_qty = payload.get("reorder_quantity")
            if not location_id or not reorder_qty:
                return False, (
                    "purchase_order requires inventory_location_id and reorder_quantity in payload"
                )
            return False, (
                "purchase_order is a supplier-side action; it requires an ERP/"
                "supplier integration that is not configured. Action recorded "
                "for HITL follow-up instead of being executed."
            )

        if action.action_type == "review_response":
            # Live reply via the Shopify Product Reviews API. The shop must
            # have the reviews app installed and grant read/write review
            # scopes; otherwise Shopify returns 4xx and we surface the honest
            # capability failure below.
            review_id = payload.get("review_id")
            reply = payload.get("draft_response") or payload.get("reply")
            if not review_id or not str(review_id).isdigit():
                return False, (
                    "review_response requires a numeric review_id and draft_response in payload"
                )
            await client.post_review_reply(str(review_id), str(reply))
            logger.info("Posted reply to review %s", review_id)
            return True, f"Posted public reply to review {review_id}"

        if action.action_type == "marketing_campaign":
            # Live campaign creation: a price rule (percentage discount) plus
            # a discount code. Codes are namespaced with the campaign to keep
            # the operation idempotent across retries.
            name = payload.get("campaign_name")
            discount_percent = payload.get("discount_percent") or payload.get("discount")
            code = payload.get("code") or "CAMPAIGN"
            if not name or discount_percent is None:
                return False, (
                    "marketing_campaign requires campaign_name and discount_percent in payload"
                )
            try:
                discount_percent = float(discount_percent)
            except (TypeError, ValueError):
                return False, "marketing_campaign discount_percent must be numeric"
            if not math.isfinite(discount_percent):
                return False, "marketing_campaign discount_percent must be finite"
            percent = min(max(discount_percent, 0.0), 100.0)
            rule_id = str(uuid.uuid4())
            rule_title = f"{name} {utc_now():%Y-%m-%d}"
            price_rule = await client.create_price_rule(
                {
                    "title": rule_title,
                    "target_type": "line_item",
                    "target_selection": "all",
                    "allocation_method": "across",
                    "value_type": "percentage",
                    "value": f"-{percent:g}",
                    "customer_selection": "all",
                    "starts_at": utc_now().isoformat(timespec="seconds") + "Z",
                }
            )
            price_rule_id = str(
                price_rule.get("price_rule", {}).get("id") or price_rule.get("id") or rule_id
            )
            discount_code = f"{code}-{rule_id[:8]}"
            await client.create_discount_code(price_rule_id, discount_code)
            logger.info(
                "Created marketing campaign %s (price rule %s, code %s)",
                name,
                price_rule_id,
                discount_code,
            )
            return True, f"Created campaign {rule_title} with code {discount_code}"

        if action.action_type == "order_swap":
            order_id = payload.get("order_id")
            swap_sku = payload.get("swap_sku")
            if order_id and str(order_id).isdigit():
                await client.update_order(str(order_id), {"tags": [f"SWAP_RECOMMENDED:{swap_sku}"]})
                return True, f"Tagged order {order_id} with swap recommendation {swap_sku}"
            return True, f"Order swap recommendation recorded for review: {swap_sku}"

        if action.action_type == "return_risk_flag":
            order_id = payload.get("order_id")
            risk_level = payload.get("risk_level", "medium")
            if order_id and str(order_id).isdigit():
                await client.update_order(str(order_id), {"tags": [f"RETURN_RISK_{risk_level.upper()}"]})
                return True, f"Tagged order {order_id} with return risk: {risk_level}"
            return True, f"Return risk flagged for order {order_id} ({risk_level})"

        if action.action_type == "cart_recovery":
            cart_id = payload.get("cart_id")
            customer_email = payload.get("customer_email") or payload.get("email")
            total_value = payload.get("total_value", payload.get("cart_total", 0.0))
            discount_code = payload.get("discount_code")
            discount_value = payload.get("discount_value", 10.0)
            strategy = payload.get("strategy", "discount_urgency")
            checkout_url = payload.get("checkout_url", "")

            # 1. Create discount code on Shopify so the coupon works at checkout
            if discount_code:
                try:
                    rule_title = f"OpsIQ Cart Recovery {cart_id}"
                    price_rule = await client.create_price_rule(
                        {
                            "title": rule_title,
                            "target_type": "line_item",
                            "target_selection": "all",
                            "allocation_method": "across",
                            "value_type": "percentage",
                            "value": f"-{float(discount_value):g}",
                            "customer_selection": "all",
                            "starts_at": utc_now().isoformat(timespec="seconds") + "Z",
                        }
                    )
                    rule_id = str(
                        price_rule.get("price_rule", {}).get("id") or price_rule.get("id", "")
                    )
                    if rule_id:
                        await client.create_discount_code(rule_id, str(discount_code))
                except Exception as e:
                    logger.warning("Could not auto-create Shopify discount for cart %s: %s", cart_id, e)

            # 2. Klaviyo Event Bridge: Dispatch event to trigger retention/SMS/Email flow
            from ecommerce_ops.connectors.klaviyo import KlaviyoClient

            klaviyo = KlaviyoClient()
            try:
                if customer_email:
                    await klaviyo.trigger_cart_recovery(
                        customer_email=str(customer_email),
                        cart_id=str(cart_id),
                        cart_total=float(total_value or 0.0),
                        discount_code=discount_code,
                        discount_value=float(discount_value or 0.0),
                        checkout_url=checkout_url,
                        recovery_strategy=strategy,
                    )
            finally:
                await klaviyo.close()

            logger.info("Triggered Klaviyo cart recovery flow for %s (cart: %s)", customer_email, cart_id)
            return True, f"Dispatched Klaviyo cart recovery for cart {cart_id} ({customer_email or 'anonymous'})"

        if action.action_type == "support_response":
            ticket_id = payload.get("ticket_id")
            draft = (
                payload.get("draft_response")
                or payload.get("response")
                or payload.get("resolution")
                or ""
            )
            sentiment = payload.get("sentiment", "neutral")
            customer_email = payload.get("customer_email") or payload.get("email")
            urgency = payload.get("urgency", "normal")

            from ecommerce_ops.connectors.gorgias import GorgiasClient

            gorgias = GorgiasClient()
            try:
                if ticket_id:
                    # Post internal note to existing Gorgias ticket with AI draft recommendation
                    note_text = (
                        f"🤖 OpsIQ Customer Support Recommendation:\n"
                        f"• Sentiment: {sentiment.upper()} | Urgency: {urgency.upper()}\n"
                        f"• Proposed Draft:\n{draft}"
                    )
                    await gorgias.add_internal_note(ticket_id, note_text)
                    await gorgias.update_ticket_tags(
                        ticket_id, ["opsiq-ai-draft", f"sentiment-{sentiment}"]
                    )
                    msg = f"Injected OpsIQ draft note and tags into Gorgias ticket #{ticket_id}"
                elif customer_email:
                    # Create new ticket in Gorgias
                    subject = payload.get("subject") or f"Support Request from {customer_email}"
                    await gorgias.create_ticket(
                        customer_email=str(customer_email),
                        subject=subject,
                        message_body=draft,
                        tags=["opsiq-ai-draft", f"sentiment-{sentiment}"],
                    )
                    msg = f"Created Gorgias ticket for {customer_email} with AI response draft"
                else:
                    msg = f"Support ticket response recorded for review (draft length: {len(draft)} chars)"
            finally:
                await gorgias.close()

            logger.info("Executed Gorgias bridge action for ticket: %s", ticket_id)
            return True, msg

        return False, f"Unknown action type: {action.action_type}"
    except Exception as e:
        METRIC_AGENT_EXECUTION_ERRORS.labels(agent=action.agent).inc()
        logger.error("Shop action %s for %s failed: %s", action.action_type, action.id, e)
        return False, str(e)
    finally:
        await client.close()


async def update_agent_streak(agent_name: str, approved: bool, confidence: float, db: AsyncSession):
    """Atomically update agent streak metrics via a single UPDATE statement.

    Uses SQL-level expressions instead of read-modify-write to avoid lost
    updates under concurrent approves (M4). SQLite and PostgreSQL both
    serialise row-level writes within a transaction.
    """
    if approved:
        stmt = (
            update(AgentStatus)
            .where(AgentStatus.agent_id == agent_name)
            .values(
                total_decisions=func.coalesce(AgentStatus.total_decisions, 0) + 1,
                total_approvals=func.coalesce(AgentStatus.total_approvals, 0) + 1,
                streak=func.coalesce(AgentStatus.streak, 0) + 1,
                avg_confidence=(
                    func.coalesce(AgentStatus.avg_confidence, 0)
                    * func.coalesce(AgentStatus.total_decisions, 0)
                    + confidence
                )
                / (func.coalesce(AgentStatus.total_decisions, 0) + 1),
            )
            .execution_options(synchronize_session=False)
        )
    else:
        stmt = (
            update(AgentStatus)
            .where(AgentStatus.agent_id == agent_name)
            .values(
                total_decisions=func.coalesce(AgentStatus.total_decisions, 0) + 1,
                total_rejections=func.coalesce(AgentStatus.total_rejections, 0) + 1,
                streak=0,
                avg_confidence=(
                    func.coalesce(AgentStatus.avg_confidence, 0)
                    * func.coalesce(AgentStatus.total_decisions, 0)
                    + confidence
                )
                / (func.coalesce(AgentStatus.total_decisions, 0) + 1),
            )
            .execution_options(synchronize_session=False)
        )
    await db.execute(stmt)

    # Check for autonomy graduation (read the updated value)
    if approved and confidence >= 0.95:
        res = await db.execute(
            select(func.coalesce(AgentStatus.streak, 0)).where(AgentStatus.agent_id == agent_name)
        )
        streak = res.scalar() or 0
        if streak >= 50:
            await db.execute(
                update(AgentStatus)
                .where(AgentStatus.agent_id == agent_name)
                .where(AgentStatus.autonomy_level != "autonomous")
                .values(autonomy_level="autonomous")
                .execution_options(synchronize_session=False)
            )
            logger.info("Agent %s graduated to AUTONOMOUS!", agent_name)
            await notify_agent_graduated(agent_name, "autonomous", streak)
    elif not approved:
        await db.execute(
            update(AgentStatus)
            .where(AgentStatus.agent_id == agent_name)
            .where(AgentStatus.autonomy_level != "supervised")
            .values(autonomy_level="supervised")
            .execution_options(synchronize_session=False)
        )


async def run_pipeline_task(run_id: str, db_settings: StoreSettings, shop_domain: Optional[str] = None):
    # Locked batch guard: prevent re-running the same pipeline
    lock = _get_pipeline_lock(run_id)
    if lock.locked():
        logger.warning("Pipeline run %s already in progress, rejecting", run_id)
        raise RuntimeError(f"Pipeline run {run_id} is already in progress")

    # Idempotency: register run in PipelineRun table (C4)
    async with async_session_factory() as session:
        pipeline_run = await _try_register_pipeline_run(run_id, session, shop_domain=shop_domain)
        if pipeline_run is None:
            logger.warning("Pipeline run %s already registered, rejecting", run_id)
            raise RuntimeError(f"Pipeline run {run_id} has already completed")
        await session.commit()

    # Fetch data OUTSIDE the lock — this is read-only I/O and should not
    # serialize unrelated pipeline runs.
    logger.info("Starting pipeline run %s (%s)", run_id, shop_domain or "default store")
    shopify_data = await fetch_shopify_data(shop_domain=shop_domain)

    if shopify_data:
        inventory_data = shopify_data["inventory_data"]
        active_orders = shopify_data["active_orders"]
        reviews_data = shopify_data["reviews_data"]
        abandoned_carts = shopify_data.get("abandoned_carts", [])
        support_tickets = []
        data_source = "shopify"
        logger.info(
            "Using Shopify data: %d inventory items, %d active orders, %d abandoned carts",
            len(inventory_data),
            len(active_orders),
            len(abandoned_carts),
        )
    else:
        if app_settings.ENV == Environment.PRODUCTION:
            raise RuntimeError(
                f"Pipeline run {run_id}: Shopify data unavailable in production and "
                "fail-open to mock data is disabled. Configure Shopify "
                "credentials or check the Shopify API."
            )
        # Fallback to mock data (development/testing only)
        inventory_data = [
            {"sku": "TSHIRT-BLUE-L", "stock": 3, "price": 25.0, "variant_id": "v1"},
            {"sku": "MUG-WHITE", "stock": 2, "price": 12.0, "variant_id": "v2"},
            {"sku": "SILK-PILLOW-SLV", "stock": 1, "price": 49.0, "variant_id": "v3"},
        ]

        active_orders = [
            {
                "id": "o_suspicious",
                "line_items": [{"sku": "TSHIRT-BLUE-L", "quantity": 1}],
                "order_total": 450.0,
            },
        ]

        reviews_data = [
            {
                "id": "r_100",
                "content": "The shipping was delayed and box was damaged!",
                "rating": 2,
            },
        ]

        abandoned_carts = [
            {
                "id": "cart_mock_1",
                "shop_domain": "mock-store.myshopify.com",
                "items": [
                    {
                        "product_id": 101,
                        "variant_id": 201,
                        "title": "Blue T-Shirt",
                        "sku": "TSHIRT-BLUE-L",
                        "quantity": 2,
                        "price": 25.0,
                        "total": 50.0,
                    },
                    {
                        "product_id": 102,
                        "variant_id": 202,
                        "title": "White Mug",
                        "sku": "MUG-WHITE",
                        "quantity": 1,
                        "price": 12.0,
                        "total": 12.0,
                    },
                ],
                "total_value": 62.0,
                "currency": "USD",
                "items_count": 2,
                "status": "abandoned",
                "checkout_url": "https://mock-store.myshopify.com/checkout/abc123",
                "customer": {
                    "email": "customer@example.com",
                    "first_name": "John",
                    "last_name": "Doe",
                    "total_orders": 3,
                    "total_spent": 150.0,
                    "is_repeat_customer": True,
                    "segment": "returning",
                },
            },
        ]

        support_tickets = [
            {
                "id": "ticket_001",
                "shop_domain": "mock-store.myshopify.com",
                "customer_email": "angry@example.com",
                "customer_name": "Sarah",
                "subject": "Where is my order?!",
                "body": "I placed my order 2 weeks ago and still haven't received it! This is unacceptable. I want a refund immediately!",
                "channel": "email",
                "order_id": "12345",
                "created_at": utc_now().isoformat(),
                "metadata": {"total_spent": 250.0, "total_orders": 5},
            },
            {
                "id": "ticket_002",
                "shop_domain": "mock-store.myshopify.com",
                "customer_email": "question@example.com",
                "customer_name": "Mike",
                "subject": "Product question",
                "body": "Hi, what sizes does the blue t-shirt come in? Also, is it machine washable?",
                "channel": "chat",
                "product_id": "101",
                "created_at": utc_now().isoformat(),
                "metadata": {"total_spent": 50.0, "total_orders": 1},
            },
        ]
        data_source = "mock"
        logger.info("Using mock data (Shopify not configured)")

    # Update PipelineRun with data source
    async with async_session_factory() as session:
        await session.execute(
            update(PipelineRun).where(PipelineRun.run_id == run_id).values(data_source=data_source)
        )
        await session.commit()

    initial_state = {
        "inventory_data": inventory_data,
        "active_orders": active_orders,
        "reviews_data": reviews_data,
        "abandoned_carts": abandoned_carts,
        "support_tickets": support_tickets,
        "decisions": [],
        "hitl_queue": [],
        "messages": [],
        "errors": [],
        "run_id": run_id,
        "timestamp": utc_now(),
    }

    try:
        # Create pipeline trace
        trace = langfuse_client.create_trace(
            name="pipeline.run",
            user_id=None,
            tags=["pipeline", run_id],
            metadata={
                "run_id": run_id,
                "data_source": data_source,
            },
        )

        supervisor = Supervisor()
        final_state = await supervisor.run(initial_state)
        decisions_list = final_state.get("decisions", [])
        logger.info("Pipeline %s finished: %d decisions", run_id, len(decisions_list))

        # Evaluate decisions
        evaluation_results = []
        for d in decisions_list:
            evaluation = evaluation_framework.evaluate_decision(
                agent_name=d.agent_id,
                decision_id=str(uuid.uuid4()),
                decision={
                    "action_type": d.action_type,
                    "reasoning": d.reasoning,
                    "confidence_score": d.confidence_score,
                    "action_data": d.action_data,
                },
                context={"run_id": run_id},
                trace_id=trace.id if trace else None,
            )
            evaluation_results.append(evaluation)

            # Add score to trace
            if trace:
                langfuse_client.score(
                    trace_id=trace.id,
                    name=f"{d.agent_id}.quality",
                    value=evaluation.overall_score,
                    comment=evaluation.feedback,
                )

        async with async_session_factory() as session:
            res_set = await session.execute(select(StoreSettings).where(StoreSettings.id == 1))
            settings = res_set.scalar_one()
            new_actions_count = 0

            # Shadow-mode A/B: compare each decision against the rule-baseline
            # variant and record which strategy would have won. Fail-open.
            if settings.shadow_mode:
                for d, evaluation in zip(decisions_list, evaluation_results, strict=False):
                    await run_ab_experiment(
                        decision=d,
                        evaluation_a=evaluation,
                        run_id=run_id,
                        session=session,
                    )

            for d in decisions_list:
                mapped_type = DECISION_TYPE_MAP.get(d.action_type)
                if mapped_type is None:
                    logger.error(
                        "Unknown action_type '%s' for agent '%s' — refusing to create action",
                        d.action_type,
                        d.agent_id,
                    )
                    continue  # skip, don't silently default to marketing_campaign
                requires_hitl, risk_level, financial_impact = evaluate_action_safety(
                    d.agent_id, mapped_type, d.action_data, d.confidence_score, settings
                )

                payload, evidence = build_payload_and_evidence(d, reviews_data)
                impact = {
                    "financial_impact": financial_impact,
                    "affected_skus": [],
                    "affected_orders": [],
                    "reversible": True,
                    "reversal_window_hours": 24,
                }
                if d.agent_id in ("FraudAgent",):
                    impact["affected_orders"] = [payload.get("order_id", "")]
                else:
                    impact["affected_skus"] = [payload.get("sku", "")] if payload.get("sku") else []

                action_id = str(uuid.uuid4())

                # Auto-approval requires BOTH: safety rules permit it AND the
                # decision confidence clears the configured threshold. Otherwise
                # the action is held for human review.
                auto_attempt = (
                    not requires_hitl
                    and not settings.shadow_mode
                    and d.confidence_score >= app_settings.AUTO_APPROVE_CONFIDENCE_SCORE
                )

                action = ApprovalAction(
                    id=action_id,
                    agent=d.agent_id,
                    action_type=mapped_type,
                    status="executing" if auto_attempt else "pending",
                    risk_level=risk_level,
                    confidence_score=d.confidence_score,
                    created_at=utc_now(),
                    expires_at=utc_now() + timedelta(days=2),
                    requires_hitl=requires_hitl,
                    shadow_mode=settings.shadow_mode,
                    payload=payload,
                    evidence=evidence,
                    impact=impact,
                )

                executed_ok = False
                execution_msg = None
                if auto_attempt:
                    # C5: Transactional outbox. Commit the action + outbox row
                    # BEFORE the live Shopify call so a crash mid-call cannot
                    # silently lose the dispatch; the OutboxSweeper redelivers
                    # rows left stuck in "pending".
                    outbox = OutboxMessage(
                        action_id=action_id,
                        status="pending",
                        payload=payload,
                    )
                    session.add(action)
                    session.add(outbox)
                    await session.commit()

                    executed_ok, execution_msg = await execute_shop_action(action)
                    action.status = "executed" if executed_ok else "failed"
                    if not executed_ok:
                        action.operator_notes = f"Auto-execution failed: {execution_msg}"
                        outbox.status = "failed"
                        outbox.error = execution_msg
                        await notify_execution_failed(
                            action_id=action_id,
                            action_type=mapped_type,
                            agent=d.agent_id,
                            error=execution_msg,
                            context="auto-execution",
                        )
                    else:
                        outbox.status = "sent"
                        outbox.sent_at = utc_now()
                        METRIC_DECISIONS_AUTO_APPROVED.labels(agent=d.agent_id).inc()
                else:
                    session.add(action)

                METRIC_DECISIONS_CREATED.labels(agent=d.agent_id, action_type=mapped_type).inc()
                METRIC_FINANCIAL_IMPACT.labels(agent=d.agent_id, action_type=mapped_type).inc(
                    financial_impact
                )

                if auto_attempt:
                    session.add(
                        AuditEntry(
                            action_id=action_id,
                            timestamp=utc_now(),
                            agent=d.agent_id,
                            action_type=mapped_type,
                            decision=("auto-approved" if executed_ok else "auto-approval-failed"),
                            operator=None,
                            confidence_score=d.confidence_score,
                            financial_impact=financial_impact,
                            details={
                                "notes": (
                                    "Auto-executed by safety system"
                                    if executed_ok
                                    else f"Auto-execution failed: {execution_msg}"
                                ),
                                "execution_status": action.status,
                                "payload": payload,
                            },
                        )
                    )
                    await update_agent_streak(d.agent_id, executed_ok, d.confidence_score, session)

                new_actions_count += 1
                if action.status == "pending":
                    await notify_hitl_request(
                        agent=d.agent_id,
                        action_id=action_id,
                        action_type=mapped_type,
                        risk_level=risk_level,
                        confidence=d.confidence_score,
                        payload=payload,
                        impact={"financial_impact": financial_impact},
                    )

            await session.commit()

            # Log evaluation summary
            avg_score = (
                sum(e.overall_score for e in evaluation_results) / len(evaluation_results)
                if evaluation_results
                else 0
            )
            passed_count = sum(1 for e in evaluation_results if e.passed)
            logger.info(
                "Pipeline %s evaluation: %d/%d passed, avg_score=%.3f",
                run_id,
                passed_count,
                len(evaluation_results),
                avg_score,
            )

            # Add pipeline completion to trace
            if trace:
                langfuse_client.create_span(
                    trace_id=trace.id,
                    name="pipeline_summary",
                    output={
                        "run_id": run_id,
                        "decisions_count": len(decisions_list),
                        "actions_count": new_actions_count,
                        "evaluation_avg_score": round(avg_score, 3),
                        "evaluation_pass_rate": round(passed_count / len(evaluation_results), 3)
                        if evaluation_results
                        else 0,
                    },
                )

            await ws_manager.broadcast(
                {
                    "type": "pipeline_completed",
                    "payload": {
                        "run_id": run_id,
                        "action_count": new_actions_count,
                        "evaluation": {
                            "avg_score": round(avg_score, 3),
                            "pass_rate": round(passed_count / len(evaluation_results), 3)
                            if evaluation_results
                            else 0,
                        },
                    },
                }
            )
            METRIC_PIPELINE_RUNS.labels(status="success").inc()

            # C4: Update PipelineRun with final stats
            await session.execute(
                update(PipelineRun)
                .where(PipelineRun.run_id == run_id)
                .values(
                    status="completed",
                    decisions_count=len(decisions_list),
                    actions_count=new_actions_count,
                    evaluation_avg_score=round(avg_score, 3),
                    evaluation_pass_rate=round(passed_count / len(evaluation_results), 3)
                    if evaluation_results
                    else 0,
                    finished_at=utc_now(),
                )
            )
            await session.commit()

    except Exception as e:
        logger.exception("Pipeline run %s failed: %s", run_id, e)
        METRIC_PIPELINE_RUNS.labels(status="failure").inc()

        # C4: Mark PipelineRun as failed
        try:
            async with async_session_factory() as session:
                await session.execute(
                    update(PipelineRun)
                    .where(PipelineRun.run_id == run_id)
                    .values(
                        status="failed",
                        error=str(e)[:500],
                        finished_at=utc_now(),
                    )
                )
                await session.commit()
        except Exception:
            logger.exception("Failed to update PipelineRun status for %s", run_id)

        # Track failure in Langfuse
        if trace:
            langfuse_client.score(
                trace_id=trace.id,
                name="pipeline_success",
                value=0.0,
                comment=f"Pipeline failed: {e!s}",
            )

        await notify_pipeline_failed(run_id, str(e))
        await ws_manager.broadcast(
            {
                "type": "pipeline_failed",
                "payload": {"run_id": run_id, "error": str(e)},
            }
        )
    finally:
        # Flush Langfuse events
        langfuse_client.flush()
