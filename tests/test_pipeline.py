"""Tests for pipeline/runner.py and pipeline/builder.py."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr

from ecommerce_ops.models.db import ApprovalAction, AuditEntry, StoreSettings
from ecommerce_ops.pipeline.builder import build_payload_and_evidence
from ecommerce_ops.pipeline.runner import (
    DECISION_TYPE_MAP,
    execute_shop_action,
    run_pipeline_task,
    update_agent_streak,
)

# ── builder.py tests ───────────────────────────────────────


def _make_decision(agent_id, action_data=None, reasoning="test reasoning"):
    return SimpleNamespace(
        agent_id=agent_id,
        action_data=action_data or {},
        reasoning=reasoning,
    )


class TestBuildPayloadAndEvidence:
    def test_fraud_agent_payload(self):
        d = _make_decision("FraudAgent", {"order_id": "ORD-123", "risk_score": 90})
        payload, evidence = build_payload_and_evidence(d, [])
        assert payload["order_id"] == "ORD-123"
        assert payload["fraud_score"] == 90
        assert payload["recommended_action"] == "hold"
        assert len(evidence) == 2
        assert evidence[0]["label"] == "Risk Score"

    def test_fraud_agent_default_order_id(self):
        d = _make_decision("FraudAgent", {})
        payload, _ = build_payload_and_evidence(d, [])
        assert payload["order_id"] == "ORD-UNKNOWN"

    def test_fraud_agent_does_not_fabricate_customer_identity(self):
        d = _make_decision("FraudAgent", {"order_id": "ORD-9", "risk_score": 85})
        payload, _ = build_payload_and_evidence(d, [])
        assert payload["customer_name"] == "unknown"
        assert payload["customer_email"] is None
        assert payload["order_total"] is None

    def test_inventory_agent_payload(self):
        d = _make_decision("InventoryAgent", {"sku": "SKU-1", "quantity_to_order": 100, "unit_cost": 15.0})
        payload, _evidence = build_payload_and_evidence(d, [])
        assert payload["sku"] == "SKU-1"
        assert payload["reorder_quantity"] == 100
        assert payload["total_po_value"] == 1500.0

    def test_inventory_agent_omits_fabricated_po_value_when_cost_unknown(self):
        d = _make_decision("InventoryAgent", {"sku": "SKU-1", "quantity_to_order": 100})
        payload, _ = build_payload_and_evidence(d, [])
        assert payload["total_po_value"] is None
        assert payload["current_stock"] is None
        assert payload["supplier_name"] is None

    def test_inventory_agent_default_qty(self):
        d = _make_decision("InventoryAgent", {})
        payload, _ = build_payload_and_evidence(d, [])
        assert payload["reorder_quantity"] == 75

    def test_pricing_agent_payload(self):
        d = _make_decision("PricingAgent", {"sku": "SKU-2", "old_price": 50, "new_price": 45})
        payload, _evidence = build_payload_and_evidence(d, [])
        assert payload["sku"] == "SKU-2"
        assert payload["current_price"] == 50
        assert payload["proposed_price"] == 45

    def test_reviews_agent_with_reviews(self):
        d = _make_decision("ReviewsAgent", {"review_id": "rev-1", "sentiment": "negative"})
        reviews = [{"content": "Bad product", "rating": 2}]
        payload, _evidence = build_payload_and_evidence(d, reviews)
        assert payload["review_id"] == "rev-1"
        assert payload["rating"] == 2
        assert payload["review_text"] == "Bad product"

    def test_reviews_agent_no_reviews(self):
        d = _make_decision("ReviewsAgent", {})
        payload, _ = build_payload_and_evidence(d, [])
        assert payload["rating"] is None

    def test_marketing_agent_fallback(self):
        d = _make_decision("MarketingAgent", {"sku": "SKU-3", "draft_copy": "Buy now!", "discount_percent": 15.0})
        payload, evidence = build_payload_and_evidence(d, [])
        assert payload["campaign_name"] == "Campaign for SKU-3"
        assert payload["discount_percent"] == 15.0
        assert len(evidence) == 2

    def test_marketing_agent_omits_fabricated_discount_when_unknown(self):
        d = _make_decision("MarketingAgent", {"sku": "SKU-3"})
        payload, _ = build_payload_and_evidence(d, [])
        assert payload["discount_percent"] is None
        assert payload["estimated_reach"] is None

    def test_unknown_agent_uses_marketing_fallback(self):
        d = _make_decision("UnknownAgent", {"sku": "SKU-X"})
        payload, _ = build_payload_and_evidence(d, [])
        assert "campaign_name" in payload


# ── runner.py tests ────────────────────────────────────────


class TestDecisonTypeMap:
    def test_all_keys_mapped(self):
        expected = {"HOLD_ORDER", "DRAFT_PO", "UPDATE_PRICE", "POST_REVIEW_RESPONSE", "DRAFT_MARKETING_CAMPAIGN"}
        assert set(DECISION_TYPE_MAP.keys()) == expected

    def test_all_values_are_strings(self):
        for v in DECISION_TYPE_MAP.values():
            assert isinstance(v, str)


class TestExecuteShopAction:
    @pytest.mark.asyncio
    async def test_shadow_mode_returns_true(self):
        action = MagicMock()
        action.shadow_mode = True
        action.action_type = "fraud_hold"
        action.id = "test-id"
        success, msg = await execute_shop_action(action)
        assert success is True
        assert "Shadow" in msg

    @pytest.mark.asyncio
    async def test_live_mode_requires_credentials(self):
        action = MagicMock()
        action.shadow_mode = False
        action.agent = "PricingAgent"
        action.action_type = "price_change"
        action.id = "test-id"
        with patch("ecommerce_ops.pipeline.runner.app_settings.SHOPIFY_SHOP_DOMAIN", ""), \
             patch("ecommerce_ops.pipeline.runner.app_settings.SHOPIFY_ACCESS_TOKEN", SecretStr("")):
            success, msg = await execute_shop_action(action)
        assert success is False
        assert "requires Shopify credentials" in msg

    @pytest.mark.asyncio
    async def test_live_mode_price_change_success(self):
        action = MagicMock()
        action.shadow_mode = False
        action.agent = "PricingAgent"
        action.action_type = "price_change"
        action.id = "test-id"
        action.payload = {"sku": "SKU1", "proposed_price": 9.99}
        with patch("ecommerce_ops.pipeline.runner.app_settings.SHOPIFY_SHOP_DOMAIN", "test-shop.myshopify.com"), \
             patch("ecommerce_ops.pipeline.runner.app_settings.SHOPIFY_ACCESS_TOKEN", SecretStr("test-token")), \
             patch("ecommerce_ops.connectors.shopify.client.ShopifyClient") as mock_client:
            mock_client.return_value.get_products = AsyncMock(return_value={
                "products": [{"id": "100", "variants": [{"id": "200", "sku": "SKU1"}]}]
            })
            mock_client.return_value.update_product = AsyncMock()
            mock_client.return_value.close = AsyncMock()
            success, msg = await execute_shop_action(action)
        assert success is True
        assert "Updated price for SKU1 to 9.99" in msg
        mock_client.return_value.update_product.assert_awaited_once_with(
            "100", {"variants": [{"id": "200", "price": "9.99"}]}
        )

    @pytest.mark.asyncio
    async def test_live_mode_denies_unlisted_agent(self):
        action = MagicMock()
        action.shadow_mode = False
        action.agent = "UnknownAgent"
        action.action_type = "price_change"
        action.id = "test-id"
        with patch("ecommerce_ops.pipeline.runner.app_settings.SHOPIFY_SHOP_DOMAIN", "test-shop.myshopify.com"), \
             patch("ecommerce_ops.pipeline.runner.app_settings.SHOPIFY_ACCESS_TOKEN", SecretStr("test-token")), \
             patch("ecommerce_ops.connectors.shopify.client.ShopifyClient") as mock_client:
            success, msg = await execute_shop_action(action)
        assert success is False
        assert "does not have permission" in msg
        mock_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_live_mode_denies_agent_outside_allowlist(self):
        action = MagicMock()
        action.shadow_mode = False
        action.agent = "ReviewsAgent"
        action.action_type = "price_change"
        action.id = "test-id"
        with patch("ecommerce_ops.pipeline.runner.app_settings.SHOPIFY_SHOP_DOMAIN", "test-shop.myshopify.com"), \
             patch("ecommerce_ops.pipeline.runner.app_settings.SHOPIFY_ACCESS_TOKEN", SecretStr("test-token")), \
             patch("ecommerce_ops.connectors.shopify.client.ShopifyClient") as mock_client:
            success, msg = await execute_shop_action(action)
        assert success is False
        assert "does not have permission" in msg
        mock_client.assert_not_called()


class TestRunPipelineTaskAutoApproval:
    """Auto-approval must actually execute, respect AUTO_APPROVE_CONFIDENCE_SCORE,
    and mark failed actions instead of fabricating an 'executed' status."""

    @staticmethod
    def _make_session(settings):
        from ecommerce_ops.models import PipelineRun

        # First call: PipelineRun INSERT (dialect-specific) → rowcount=1
        insert_result = MagicMock()
        insert_result.rowcount = 1

        # Second call: PipelineRun SELECT → returns PipelineRun object
        pipeline_run_obj = MagicMock(spec=PipelineRun)
        pipeline_run_obj.run_id = "run-1"

        select_pr_result = MagicMock()
        select_pr_result.scalar_one.return_value = pipeline_run_obj

        # Third call: PipelineRun UPDATE (data_source)
        update_ds_result = MagicMock()
        update_ds_result.rowcount = 1

        # Fourth call: StoreSettings SELECT
        settings_result = MagicMock()
        settings_result.scalar_one.return_value = settings

        # Fifth call: PipelineRun UPDATE (final stats)
        update_final_result = MagicMock()
        update_final_result.rowcount = 1

        session = MagicMock()
        session.execute = AsyncMock(
            side_effect=[
                insert_result,
                select_pr_result,
                update_ds_result,
                settings_result,
                update_final_result,
            ]
        )
        session.commit = AsyncMock()
        session.flush = AsyncMock()
        session.add = MagicMock()
        session_mgr = MagicMock()
        session_mgr.__aenter__ = AsyncMock(return_value=session)
        session_mgr.__aexit__ = AsyncMock(return_value=False)
        return session, MagicMock(return_value=session_mgr)

    @staticmethod
    def _decision(confidence):
        return SimpleNamespace(
            agent_id="PricingAgent",
            action_type="UPDATE_PRICE",
            action_data={"sku": "SKU-1", "old_price": 10.0, "new_price": 10.5},
            reasoning="elasticity analysis",
            confidence_score=confidence,
        )

    @staticmethod
    def _added_objects(session):
        added = [c.args[0] for c in session.add.call_args_list]
        return (
            [a for a in added if isinstance(a, ApprovalAction)],
            [a for a in added if isinstance(a, AuditEntry)],
        )

    def _settings(self):
        return StoreSettings(
            id=1, shadow_mode=False, fraud_threshold=70,
            po_limit=1000.0, pricing_limit=5.0, reviews_rating_threshold=4,
        )

    @pytest.mark.asyncio
    async def _run(self, confidence, factory, execute_return):
        import contextlib
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch("ecommerce_ops.pipeline.runner.async_session_factory", factory))
            stack.enter_context(patch("ecommerce_ops.pipeline.runner.fetch_shopify_data",
                                      new_callable=AsyncMock, return_value=None))
            stack.enter_context(patch("ecommerce_ops.pipeline.runner.langfuse_client", MagicMock()))
            stack.enter_context(patch("ecommerce_ops.pipeline.runner.ws_manager.broadcast",
                                      new_callable=AsyncMock))
            stack.enter_context(patch("ecommerce_ops.pipeline.runner.notify_hitl_request",
                                      new_callable=AsyncMock))
            stack.enter_context(patch("ecommerce_ops.pipeline.runner.notify_pipeline_failed",
                                      new_callable=AsyncMock))
            stack.enter_context(patch("ecommerce_ops.pipeline.runner.evaluation_framework.evaluate_decision",
                                      return_value=MagicMock(overall_score=0.9, passed=True, feedback="ok")))
            supervisor = stack.enter_context(patch("ecommerce_ops.pipeline.runner.Supervisor"))
            mock_exec = stack.enter_context(
                patch("ecommerce_ops.pipeline.runner.execute_shop_action", new_callable=AsyncMock)
            )
            supervisor.return_value.run = AsyncMock(
                return_value={"decisions": [self._decision(confidence)], "hitl_queue": []}
            )
            mock_exec.return_value = execute_return
            await run_pipeline_task("run-1", self._settings())
            return mock_exec

    @pytest.mark.asyncio
    async def test_high_confidence_executes_action(self):
        session, factory = self._make_session(self._settings())
        mock_exec = await self._run(0.96, factory, (True, "done"))
        actions, entries = self._added_objects(session)
        assert len(actions) == 1
        assert actions[0].status == "executed"
        assert actions[0].operator_notes is None
        assert mock_exec.await_count == 1
        assert entries[0].decision == "auto-approved"
        assert entries[0].details["execution_status"] == "executed"

    @pytest.mark.asyncio
    async def test_high_confidence_failure_marks_failed(self):
        session, factory = self._make_session(self._settings())
        await self._run(0.96, factory, (False, "Shopify not configured"))
        actions, entries = self._added_objects(session)
        assert actions[0].status == "failed"
        assert "Shopify not configured" in actions[0].operator_notes
        assert entries[0].decision == "auto-approval-failed"

    @pytest.mark.asyncio
    async def test_low_confidence_held_for_review(self):
        session, factory = self._make_session(self._settings())
        mock_exec = await self._run(0.5, factory, (True, "done"))
        actions, entries = self._added_objects(session)
        assert actions[0].status == "pending"
        assert entries == []
        mock_exec.assert_not_called()


class TestUpdateAgentStreak:
    @pytest.mark.asyncio
    async def test_approved_increments_streak(self):
        session = AsyncMock()
        # First execute() call is the UPDATE (returns a mock result).
        # Second execute() call is the SELECT for streak check (returns scalar).
        update_result = MagicMock()
        select_result = MagicMock()
        select_result.scalar.return_value = 1
        session.execute.side_effect = [update_result, select_result]

        await update_agent_streak("FraudAgent", True, 0.96, session)

        assert session.execute.call_count == 2
        session.commit.assert_not_called()  # committed by caller

    @pytest.mark.asyncio
    async def test_rejected_resets_streak(self):
        session = AsyncMock()
        session.execute.side_effect = [MagicMock(), MagicMock()]

        await update_agent_streak("FraudAgent", False, 0.5, session)

        # UPDATE for streak reset + UPDATE for autonomy-level downgrade
        assert session.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_graduation_to_autonomous(self):
        session = AsyncMock()
        update_result = MagicMock()
        select_result = MagicMock()
        select_result.scalar.return_value = 50
        session.execute.side_effect = [update_result, select_result, MagicMock()]

        with patch("ecommerce_ops.pipeline.runner.notify_agent_graduated", new_callable=AsyncMock):
            await update_agent_streak("FraudAgent", True, 0.99, session)

        assert session.execute.call_count == 3

    @pytest.mark.asyncio
    async def test_nonexistent_agent_does_nothing(self):
        # The atomic UPDATE simply affects zero rows when the agent doesn't
        # exist — no exception, no error.
        session = AsyncMock()
        session.execute.return_value = MagicMock()

        await update_agent_streak("NonexistentAgent", True, 0.9, session)
        assert session.execute.call_count >= 1
