"""Tests for week 8–9: live-execution breadth, execution metrics,
shadow-mode A/B experiments, and full server credential rotation.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ecommerce_ops.observability.ab_testing import (
    build_baseline_decision,
    run_ab_experiment,
)
from ecommerce_ops.observability.evaluation import evaluation_framework
from ecommerce_ops.pipeline.runner import execute_shop_action
from ecommerce_ops.security.credential_store import ServerCredentialStore


def _live_action(action_type: str, agent: str, payload: dict) -> MagicMock:
    action = MagicMock()
    action.shadow_mode = False
    action.action_type = action_type
    action.agent = agent
    action.id = "test-action"
    action.payload = payload
    return action


def _patch_shopify(overrides: dict | None = None):
    client = MagicMock()
    methods = [
        "get_products",
        "update_product",
        "update_order",
        "post_review_reply",
        "create_price_rule",
        "create_discount_code",
    ]
    for name in methods:
        setattr(client.return_value, name, AsyncMock(return_value={}))
    client.return_value.close = AsyncMock()
    for name, ret in (overrides or {}).items():
        setattr(client.return_value, name, AsyncMock(return_value=ret))
    return (
        patch("ecommerce_ops.connectors.shopify.client.ShopifyClient", client),
        client,
    )


class TestLiveExecutionBreadth:
    """Week 8 — review_response and marketing_campaign now execute for real;
    purchase_order stays an honest capability failure (ERP not configured)."""

    @pytest.mark.asyncio
    async def test_review_response_posts_reply(self):
        action = _live_action(
            "review_response",
            "ReviewsAgent",
            {"review_id": "1234", "draft_response": "Thanks for your feedback!"},
        )
        mock_patch, client = _patch_shopify({"post_review_reply": {"ok": True}})
        with (
            patch("ecommerce_ops.pipeline.runner.app_settings.SHOPIFY_SHOP_DOMAIN", "s.myshopify.com"),
            patch("ecommerce_ops.pipeline.runner.app_settings.SHOPIFY_ACCESS_TOKEN", SecretStr("tok")),
            mock_patch,
        ):
            ok, msg = await execute_shop_action(action)
        assert ok is True
        assert "Posted public reply to review 1234" in msg
        client.return_value.post_review_reply.assert_awaited_once_with(
            "1234", "Thanks for your feedback!"
        )

    @pytest.mark.asyncio
    async def test_review_response_requires_numeric_review_id(self):
        action = _live_action("review_response", "ReviewsAgent", {"draft_response": "hi"})
        mock_patch, client = _patch_shopify()
        with (
            patch("ecommerce_ops.pipeline.runner.app_settings.SHOPIFY_SHOP_DOMAIN", "s.myshopify.com"),
            patch("ecommerce_ops.pipeline.runner.app_settings.SHOPIFY_ACCESS_TOKEN", SecretStr("tok")),
            mock_patch,
        ):
            ok, msg = await execute_shop_action(action)
        assert ok is False
        assert "review_id" in msg
        client.return_value.post_review_reply.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_marketing_campaign_creates_price_rule_and_code(self):
        action = _live_action(
            "marketing_campaign",
            "MarketingAgent",
            {"campaign_name": "Summer Sale", "discount_percent": 15.0},
        )
        mock_patch, client = _patch_shopify({
            "create_price_rule": {"price_rule": {"id": 555}},
            "create_discount_code": {"discount_code": {"code": "SUMMER-X"}},
        })
        with (
            patch("ecommerce_ops.pipeline.runner.app_settings.SHOPIFY_SHOP_DOMAIN", "s.myshopify.com"),
            patch("ecommerce_ops.pipeline.runner.app_settings.SHOPIFY_ACCESS_TOKEN", SecretStr("tok")),
            mock_patch,
        ):
            ok, msg = await execute_shop_action(action)
        assert ok is True
        assert "Created campaign" in msg
        client.return_value.create_price_rule.assert_awaited_once()
        client.return_value.create_discount_code.assert_awaited_once()
        rule_body = client.return_value.create_price_rule.await_args.args[0]
        assert rule_body["value"] == "-15"
        code_args = client.return_value.create_discount_code.await_args.args
        assert code_args[0] == "555"
        assert code_args[1].startswith("CAMPAIGN-")

    @pytest.mark.asyncio
    async def test_marketing_campaign_validates_numeric_discount(self):
        action = _live_action(
            "marketing_campaign", "MarketingAgent", {"campaign_name": "Sale", "discount_percent": "NaN"}
        )
        mock_patch, client = _patch_shopify()
        with (
            patch("ecommerce_ops.pipeline.runner.app_settings.SHOPIFY_SHOP_DOMAIN", "s.myshopify.com"),
            patch("ecommerce_ops.pipeline.runner.app_settings.SHOPIFY_ACCESS_TOKEN", SecretStr("tok")),
            mock_patch,
        ):
            ok, msg = await execute_shop_action(action)
        assert ok is False
        assert "finite" in msg
        client.return_value.create_price_rule.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_purchase_order_stays_honest_capability_failure(self):
        action = _live_action(
            "purchase_order",
            "InventoryAgent",
            {"inventory_location_id": "loc-1", "reorder_quantity": 100},
        )
        mock_patch, client = _patch_shopify()
        with (
            patch("ecommerce_ops.pipeline.runner.app_settings.SHOPIFY_SHOP_DOMAIN", "s.myshopify.com"),
            patch("ecommerce_ops.pipeline.runner.app_settings.SHOPIFY_ACCESS_TOKEN", SecretStr("tok")),
            mock_patch,
        ):
            ok, msg = await execute_shop_action(action)
        assert ok is False
        assert "ERP" in msg
        client.return_value.create_price_rule.assert_not_awaited()
        client.return_value.create_discount_code.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_purchase_order_validates_required_fields(self):
        action = _live_action("purchase_order", "InventoryAgent", {})
        mock_patch, client = _patch_shopify()
        with (
            patch("ecommerce_ops.pipeline.runner.app_settings.SHOPIFY_SHOP_DOMAIN", "s.myshopify.com"),
            patch("ecommerce_ops.pipeline.runner.app_settings.SHOPIFY_ACCESS_TOKEN", SecretStr("tok")),
            mock_patch,
        ):
            ok, msg = await execute_shop_action(action)
        assert ok is False
        assert "inventory_location_id" in msg


class TestAbExperiment:
    """Week 8 — shadow A/B framework records winner + divergence, fail-open."""

    def test_build_baseline_vetoes_low_confidence(self):
        decision = {"action_type": "price_change", "confidence_score": 0.4, "reasoning": "x"}
        baseline = build_baseline_decision(decision, {"min_confidence": 0.75})
        assert baseline["action_type"] == "no_op"
        assert baseline["vetoed"] is True

    def test_build_baseline_passes_high_confidence(self):
        decision = {"action_type": "price_change", "confidence_score": 0.9, "reasoning": "x"}
        baseline = build_baseline_decision(decision, {"min_confidence": 0.75})
        assert baseline["action_type"] == "price_change"
        assert "vetoed" not in baseline

    @staticmethod
    def _evaluation(confidence: float):
        return evaluation_framework.evaluate_decision(
            agent_name="PricingAgent",
            decision_id="d1",
            decision={
                "action_type": "UPDATE_PRICE",
                "reasoning": "elasticity",
                "confidence_score": confidence,
            },
            context={"run_id": "r-1"},
        )

    @pytest.mark.asyncio
    async def test_run_ab_experiment_persists_row(self, db_session):
        decision = SimpleNamespace(
            agent_id="PricingAgent",
            action_type="UPDATE_PRICE",
            confidence_score=0.5,
            reasoning="elasticity",
            action_data={"sku": "SKU-1"},
        )
        row = await run_ab_experiment(
            decision=decision,
            evaluation_a=self._evaluation(0.5),
            run_id="r-1",
            session=db_session,
        )
        assert row is not None
        assert row.run_id == "r-1"
        assert row.agent_name == "PricingAgent"
        assert row.action_type == "UPDATE_PRICE"
        assert row.winner in ("A", "B", "tie")
        assert 0.0 <= row.divergence <= 1.0
        await db_session.commit()

    @pytest.mark.asyncio
    async def test_run_ab_experiment_fail_open_on_error(self, db_session):
        decision = SimpleNamespace(
            agent_id="PricingAgent",
            action_type="UPDATE_PRICE",
            confidence_score=0.9,
            reasoning="x",
            action_data={},
        )
        evaluation_a = self._evaluation(0.9)
        with patch(
            "ecommerce_ops.observability.ab_testing.evaluation_framework.evaluate_decision",
            side_effect=RuntimeError("boom"),
        ):
            row = await run_ab_experiment(
                decision=decision,
                evaluation_a=evaluation_a,
                run_id="r-2",
                session=db_session,
            )
        assert row is None


@pytest_asyncio.fixture
async def credential_factory():
    """Fresh in-memory SQLite factory, patched into the credential store."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    from ecommerce_ops.models.db import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield factory
    await engine.dispose()


class TestServerCredentialRotation:
    """Week 9 — full credential rotation: dual-key grace window + cutover."""

    @pytest_asyncio.fixture
    async def store(self, credential_factory):
        store = ServerCredentialStore()
        with patch("ecommerce_ops.security.credential_store.async_session_factory", credential_factory):
            yield store
        store._cache = {}
        store._cache_loaded = 0.0

    @pytest.mark.asyncio
    async def test_issue_and_verify_active(self, store):
        key, prefix = await store.issue(grace_days=7)
        assert key.startswith("eops_")
        assert prefix == f"{key[:12]}..."
        assert await store.verify(key) is True
        assert await store.verify("eops_wrong_key_000000000000000000000000000") is False

    @pytest.mark.asyncio
    async def test_grace_window_accepts_previous_key(self, store):
        key_a, _ = await store.issue(grace_days=7)
        key_b, _ = await store.start_rotation(grace_days=7)
        # New key active, previous key still valid during grace (zero-downtime).
        assert await store.verify(key_b) is True
        assert await store.verify(key_a) is True

    @pytest.mark.asyncio
    async def test_finalize_revokes_previous_key(self, store):
        key_a, _ = await store.issue(grace_days=7)
        key_b, _ = await store.start_rotation(grace_days=7)
        revoked = await store.finalize_rotation()
        assert revoked >= 1
        # Cutover: rotated (previous) key no longer authenticates.
        assert await store.verify(key_a) is False
        assert await store.verify(key_b) is True

    @pytest.mark.asyncio
    async def test_rotated_key_expires_after_grace(self, credential_factory):
        from datetime import timedelta

        from sqlalchemy import update

        from ecommerce_ops.models import ServerCredential
        from ecommerce_ops.utils import utc_now

        store = ServerCredentialStore()
        with patch("ecommerce_ops.security.credential_store.async_session_factory", credential_factory):
            key_a, _ = await store.issue(grace_days=1)
            key_b, _ = await store.start_rotation(grace_days=1)
            # Force the grace window to lapse.
            async with credential_factory() as session:
                await session.execute(
                    update(ServerCredential)
                    .where(ServerCredential.status == "rotated")
                    .values(valid_until=utc_now() - timedelta(seconds=1))
                )
                await session.commit()
            store._cache = {}
            store._cache_loaded = 0.0
            assert await store.verify(key_a) is False
            assert await store.verify(key_b) is True

    @pytest.mark.asyncio
    async def test_list_credentials_never_exposes_raw_key(self, store):
        await store.issue(grace_days=7)
        await store.start_rotation(grace_days=7)
        creds = await store.list_credentials()
        assert len(creds) == 2
        for c in creds:
            assert c["key_prefix"].endswith("...")
            assert c["key_prefix"].startswith("eops_")