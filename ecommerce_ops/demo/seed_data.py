"""Expanded demo seed data for realistic dashboard population."""

import random
import uuid
from datetime import timedelta

from sqlalchemy import func, select

from ecommerce_ops.models.db import (
    AgentStatus,
    ApprovalAction,
    AuditEntry,
    OutboxMessage,
    StoreSettings,
    async_session_factory,
)
from ecommerce_ops.utils import utc_now

AGENTS = ["FraudAgent", "InventoryAgent", "PricingAgent", "ReviewsAgent", "MarketingAgent"]
AGENT_DISPLAY = {
    "FraudAgent": "Fraud Detection",
    "InventoryAgent": "Inventory Management",
    "PricingAgent": "Price Optimization",
    "ReviewsAgent": "Review Moderation",
    "MarketingAgent": "Marketing Automation",
}

ACTION_TYPES = {
    "FraudAgent": ["fraud_hold", "fraud_review", "order_flag"],
    "InventoryAgent": ["purchase_order", "reorder", "stock_adjustment"],
    "PricingAgent": ["price_change", "discount_adjustment", "competitor_match"],
    "ReviewsAgent": ["review_response", "review_flag", "sentiment_alert"],
    "MarketingAgent": ["marketing_campaign", "email_blast", "audience_segment"],
}

RISK_LEVELS = ["low", "medium", "high", "critical"]
DECISIONS = ["approved", "rejected", "auto-approved", "shadow"]
PRODUCTS = [
    ("ORGANIC-TSHIRT-WHT", "Organic Cotton T-Shirt", 28.00),
    ("LEATHER-WALLET-BRN", "Genuine Leather Wallet", 65.00),
    ("YOGA-MAT-GRN", "Premium Yoga Mat", 45.00),
    ("STAINLESS-MUG-SLV", "Stainless Steel Travel Mug", 32.00),
    ("SILK-PILLOWCASE", "Mulberry Silk Pillowcase", 49.00),
    ("BAMBOO-CUTLERY", "Bamboo Cutlery Set", 18.00),
    ("NATURAL-CANDLE", "Soy Wax Scented Candle", 24.00),
    ("LINEN-TOWEL-WHT", "Bath Linen Towel Set", 55.00),
]


async def seed_expanded_demo():
    """Seed the database with expanded demo data for a rich dashboard."""
    async with async_session_factory() as session:
        res = await session.execute(select(func.count(ApprovalAction.id)))
        count = res.scalar() or 0
        if count >= 20:
            return {"status": "already_seeded", "actions": count}

        now = utc_now()
        actions = []
        audits = []

        # Generate 30 approval actions over the last 7 days
        for _i in range(30):
            agent = random.choice(AGENTS)
            action_type = random.choice(ACTION_TYPES[agent])
            risk = random.choice(RISK_LEVELS)
            confidence = round(random.uniform(0.65, 0.99), 2)
            created = now - timedelta(
                hours=random.randint(0, 168),
                minutes=random.randint(0, 59),
            )
            status = random.choices(
                ["pending", "executed", "rejected", "expired"],
                weights=[30, 40, 20, 10],
            )[0]

            product = random.choice(PRODUCTS)
            order_total = round(random.uniform(25, 500), 2)

            payload = {
                "order_id": f"ORD-{random.randint(90000, 99999)}",
                "product_name": product[1],
                "sku": product[0],
                "order_total": order_total,
                "fraud_score": random.randint(20, 98),
                "risk_signals": random.sample(
                    [
                        "IP mismatch",
                        "VPN detected",
                        "New account",
                        "Bulk order",
                        "Velocity spike",
                        "Address mismatch",
                        "Card decline history",
                    ],
                    k=random.randint(1, 3),
                ),
            }

            impact_val = round(random.uniform(-2000, 3000), 2)

            action = ApprovalAction(
                id=str(uuid.uuid4()),
                agent=agent,
                action_type=action_type,
                status=status,
                risk_level=risk,
                confidence_score=confidence,
                created_at=created,
                expires_at=created + timedelta(days=random.randint(1, 7)),
                requires_hitl=risk in ("high", "critical"),
                shadow_mode=random.random() > 0.3,
                payload=payload,
                evidence=[
                    {
                        "label": "Confidence",
                        "value": str(confidence),
                        "weight": "primary",
                        "source": "AgentEngine",
                    }
                ],
                impact={"financial_impact": impact_val, "affected_skus": [product[0]]},
                reviewed_by="admin" if status in ("executed", "rejected") else None,
                reviewed_at=created + timedelta(minutes=random.randint(5, 60))
                if status in ("executed", "rejected")
                else None,
            )
            actions.append(action)

            # Matching audit entry
            audits.append(
                AuditEntry(
                    action_id=action.id,
                    timestamp=action.reviewed_at or created,
                    agent=agent,
                    action_type=action_type,
                    decision=random.choice(DECISIONS) if status != "pending" else "shadow",
                    operator=action.reviewed_by,
                    confidence_score=confidence,
                    financial_impact=impact_val,
                    details={"demo": True, "product": product[1]},
                )
            )

        # Ensure agent statuses exist
        for agent in AGENTS:
            existing = await session.execute(
                select(AgentStatus).where(AgentStatus.agent_id == agent)
            )
            if not existing.scalar_one_or_none():
                session.add(
                    AgentStatus(
                        agent_id=agent,
                        status="active",
                        streak=random.randint(0, 25),
                        autonomy_level=random.choice(["shadow", "supervised", "autonomous"]),
                        total_decisions=random.randint(50, 500),
                        total_approvals=random.randint(30, 400),
                        total_rejections=random.randint(5, 100),
                        avg_confidence=round(random.uniform(0.80, 0.98), 2),
                    )
                )

        # Ensure store settings exist
        existing_settings = await session.execute(
            select(StoreSettings).where(StoreSettings.id == 1)
        )
        if not existing_settings.scalar_one_or_none():
            session.add(
                StoreSettings(
                    id=1,
                    shadow_mode=True,
                    fraud_threshold=70,
                    po_limit=1000.0,
                    pricing_limit=5.0,
                    reviews_rating_threshold=4,
                )
            )

        session.add_all(actions)
        session.add_all(audits)

        # Seed orphaned outbox rows (older than the sweep window) so the
        # distributed-lock-guarded OutboxSweeper has redeliverable work.
        outbox_rows = []
        for i in range(3):
            action = actions[i]
            outbox_rows.append(
                OutboxMessage(
                    action_id=action.id,
                    status="pending",
                    payload=action.payload,
                    created_at=now - timedelta(hours=2 + i),
                    retry_count=0,
                )
            )
        session.add_all(outbox_rows)

        await session.commit()

        return {
            "status": "seeded",
            "actions_created": len(actions),
            "audits_created": len(audits),
            "outbox_created": len(outbox_rows),
            "agents": len(AGENTS),
        }
