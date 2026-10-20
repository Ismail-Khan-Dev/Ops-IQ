import logging
from datetime import timedelta

from sqlalchemy import select

from ecommerce_ops.config import Environment, settings
from ecommerce_ops.models.db import ApprovalAction, AuditEntry, async_session_factory
from ecommerce_ops.utils import utc_now

logger = logging.getLogger("ecommerce_ops.seed")


async def seed_data_if_empty():
    if settings.ENV == Environment.PRODUCTION:
        logger.info("Skipping mock seeding in production environment.")
        return

    async with async_session_factory() as session:
        # Check if we already have actions
        res = await session.execute(select(ApprovalAction))
        actions = res.scalars().all()
        if actions:
            logger.info("Database already seeded. Skipping mock seeding.")
            return

        logger.info("Seeding database with mock operations actions...")

        now = utc_now()

        mock_actions = [
            # 1. Pending Fraud Hold (High Risk)
            ApprovalAction(
                id="a1b2c3d4-0001-4000-8000-000000000001",
                agent="FraudAgent",
                action_type="fraud_hold",
                status="pending",
                risk_level="high",
                confidence_score=0.92,
                created_at=now - timedelta(minutes=15),
                expires_at=now + timedelta(hours=23, minutes=45),
                requires_hitl=True,
                shadow_mode=True,
                payload={
                    "order_id": "ORD-94827",
                    "customer_name": "Alexander Sterling",
                    "customer_email": "alex.sterling.temp@vpnmail.net",
                    "order_total": 450.00,
                    "fraud_score": 82,
                    "risk_signals": [
                        "Billing/Shipping mismatch",
                        "VPN connection detected",
                        "High order velocity",
                    ],
                    "recommended_action": "hold",
                },
                evidence=[
                    {
                        "label": "Billing Country",
                        "value": "US (Billing) vs. UA (IP)",
                        "weight": "primary",
                        "source": "FraudHeuristics v1.2",
                    },
                    {
                        "label": "Connection",
                        "value": "Commercial VPN Host (NordVPN)",
                        "weight": "primary",
                        "source": "IPGeoLocator",
                    },
                    {
                        "label": "Card Attempts",
                        "value": "3 failed attempts before success",
                        "weight": "supporting",
                        "source": "Stripe Gateway",
                    },
                ],
                impact={
                    "financial_impact": 450.00,
                    "affected_skus": ["TSHIRT-BLUE-L", "HOODIE-GRAY-XL"],
                    "affected_orders": ["ORD-94827"],
                    "reversible": True,
                    "reversal_window_hours": 24,
                },
            ),
            # 2. Critical Risk Fraud Hold (Requires 'APPROVE' typing)
            ApprovalAction(
                id="a1b2c3d4-0002-4000-8000-000000000002",
                agent="FraudAgent",
                action_type="fraud_hold",
                status="pending",
                risk_level="critical",
                confidence_score=0.98,
                created_at=now - timedelta(minutes=5),
                expires_at=now + timedelta(hours=2),
                requires_hitl=True,
                shadow_mode=True,
                payload={
                    "order_id": "ORD-94911",
                    "customer_name": "Dmitry Vlasov",
                    "customer_email": "vlasov_dmitry99@mail.ru",
                    "order_total": 2450.00,
                    "fraud_score": 98,
                    "risk_signals": [
                        "Stolen credit card match",
                        "Blacklisted shipping address",
                        "Bulk electronics purchase",
                    ],
                    "recommended_action": "cancel",
                },
                evidence=[
                    {
                        "label": "Card Status",
                        "value": "Listed on DarkWeb Stolen Card Dump (Stripe Radar)",
                        "weight": "primary",
                        "source": "Stripe API",
                    },
                    {
                        "label": "Address Status",
                        "value": "Known reshipper address (Delaware Warehouse)",
                        "weight": "primary",
                        "source": "SiftScience",
                    },
                    {
                        "label": "Order Size",
                        "value": "5x average store order value",
                        "weight": "contextual",
                        "source": "StoreAnalytics",
                    },
                ],
                impact={
                    "financial_impact": 2450.00,
                    "affected_skus": ["PHONE-CASE-15PRO", "LAPTOP-STAND-SLV", "LEATHER-BAG-BRN"],
                    "affected_orders": ["ORD-94911"],
                    "reversible": False,
                    "reversal_window_hours": 0,
                },
            ),
            # 3. Pending Inventory Purchase Order (Medium Risk, exceeding $1000)
            ApprovalAction(
                id="a1b2c3d4-0003-4000-8000-000000000003",
                agent="InventoryAgent",
                action_type="purchase_order",
                status="pending",
                risk_level="medium",
                confidence_score=0.88,
                created_at=now - timedelta(hours=2),
                expires_at=now + timedelta(days=2),
                requires_hitl=True,
                shadow_mode=True,
                payload={
                    "sku": "GLASS-MUG-WHT",
                    "product_name": "Double-Walled Glass Coffee Mug (12oz)",
                    "current_stock": 4,
                    "daily_velocity": 8.5,
                    "days_of_supply": 0.5,
                    "reorder_quantity": 300,
                    "supplier_name": "Aurora Glassware Ltd.",
                    "unit_cost": 4.50,
                    "total_po_value": 1350.00,
                },
                evidence=[
                    {
                        "label": "Stockout Projection",
                        "value": "Out of stock in < 12 hours",
                        "weight": "primary",
                        "source": "InventoryForecaster",
                    },
                    {
                        "label": "Sales Velocity",
                        "value": "8.5 units/day (rolling 30-day average)",
                        "weight": "primary",
                        "source": "StoreAnalytics",
                    },
                    {
                        "label": "Supplier Lead Time",
                        "value": "10 business days to delivery",
                        "weight": "supporting",
                        "source": "SupplierPortal",
                    },
                ],
                impact={
                    "financial_impact": -1350.00,
                    "affected_skus": ["GLASS-MUG-WHT"],
                    "affected_orders": [],
                    "reversible": True,
                    "reversal_window_hours": 12,
                },
            ),
            # 4. Pending Pricing Change (Low Risk, exceeds settings limit of 5% but below 20%)
            ApprovalAction(
                id="a1b2c3d4-0004-4000-8000-000000000004",
                agent="PricingAgent",
                action_type="price_change",
                status="pending",
                risk_level="low",
                confidence_score=0.85,
                created_at=now - timedelta(minutes=45),
                expires_at=now + timedelta(days=1),
                requires_hitl=True,
                shadow_mode=True,
                payload={
                    "sku": "SILK-PILLOW-SLV",
                    "product_name": "Mulberry Silk Pillowcase (Silver, Standard)",
                    "current_price": 49.00,
                    "proposed_price": 45.00,
                    "change_percent": -8.16,
                    "reasoning": "Competitor 'SleepLuxe' dropped price to $44.99. Decreasing price by 8% to match competitor while retaining our 45% margin target.",
                    "competitor_prices": [
                        {"competitor": "SleepLuxe Store", "price": 44.99},
                        {"competitor": "DreamSatin", "price": 48.00},
                        {"competitor": "AuraBedding", "price": 52.00},
                    ],
                },
                evidence=[
                    {
                        "label": "Competitor Price",
                        "value": "SleepLuxe lowered price to $44.99 (-8.2%)",
                        "weight": "primary",
                        "source": "CompetitorScraper",
                    },
                    {
                        "label": "Target Margin",
                        "value": "Remaining margin: 45.3% (Target floor is 40.0%)",
                        "weight": "primary",
                        "source": "MarginValidator",
                    },
                    {
                        "label": "Sales Impact",
                        "value": "Expected conversion increase: +14%",
                        "weight": "supporting",
                        "source": "PriceElasticityModel",
                    },
                ],
                impact={
                    "financial_impact": -400.00,  # Estimated short-term margin difference vs conversion gain
                    "affected_skus": ["SILK-PILLOW-SLV"],
                    "affected_orders": [],
                    "reversible": True,
                    "reversal_window_hours": 168,
                },
            ),
            # 5. Pending Reviews Response (Medium Risk, negative review < 4★)
            ApprovalAction(
                id="a1b2c3d4-0005-4000-8000-000000000005",
                agent="ReviewsAgent",
                action_type="review_response",
                status="pending",
                risk_level="medium",
                confidence_score=0.91,
                created_at=now - timedelta(hours=4),
                expires_at=now + timedelta(days=3),
                requires_hitl=True,
                shadow_mode=True,
                payload={
                    "review_id": "rev_77391",
                    "product_name": "Premium Leather Travel Duffle Bag",
                    "rating": 2,
                    "customer_name": "Marcus Vance",
                    "sentiment": "negative",
                    "review_text": "The bag looks great but the metal zipper broke on my very first trip. Very disappointed given the premium price.",
                    "key_issues": ["Zipper broken", "Quality disappointment"],
                    "draft_response": "Hi Marcus, thank you for sharing your feedback. We are sincerely sorry to hear about the broken zipper on your travel bag. Quality is our top priority and we'd love to make this right. Please contact our support team at support@store.com and we will immediately ship you a free replacement or issue a full refund.",
                },
                evidence=[
                    {
                        "label": "Review Rating",
                        "value": "2 / 5 stars",
                        "weight": "primary",
                        "source": "ShopifyReviews API",
                    },
                    {
                        "label": "Sentiment",
                        "value": "Negative (Keywords: broke, disappointed)",
                        "weight": "primary",
                        "source": "DeepSeek NLP v3",
                    },
                    {
                        "label": "Refund Offer",
                        "value": "Draft proposes refund or free replacement",
                        "weight": "supporting",
                        "source": "SupportPolicyEngine",
                    },
                ],
                impact={
                    "financial_impact": -120.00,  # Cost of bag replacement/refund
                    "affected_skus": ["LEATHER-BAG-BRN"],
                    "affected_orders": [],
                    "reversible": False,
                    "reversal_window_hours": 0,
                },
            ),
            # 6. Pending Marketing Campaign (Medium Risk, always HITL)
            ApprovalAction(
                id="a1b2c3d4-0006-4000-8000-000000000006",
                agent="MarketingAgent",
                action_type="marketing_campaign",
                status="pending",
                risk_level="medium",
                confidence_score=0.87,
                created_at=now - timedelta(hours=6),
                expires_at=now + timedelta(days=2),
                requires_hitl=True,
                shadow_mode=True,
                payload={
                    "campaign_name": "Sateen Sheets Flash Clearance",
                    "target_skus": ["SATEEN-SHEET-WHT-Q", "SATEEN-SHEET-GRY-Q"],
                    "discount_percent": 15.0,
                    "urgency_reason": "High inventory overhead: 85 units excess stock on Gray Sateen Sheets",
                    "estimated_reach": 12500,
                    "draft_message": "Subject: Flash Sale! 15% off Sateen Sheet Sets 🛏️\n\nHi {{customer.first_name}},\n\nReady to upgrade your sleep? For the next 48 hours only, take 15% off our best-selling Sateen Sheet Sets. Sleep in luxury and comfort.\n\nUse code SLEEP15 at checkout. Only while supplies last!",
                },
                evidence=[
                    {
                        "label": "Excess Inventory",
                        "value": "85 units above safety stock threshold",
                        "weight": "primary",
                        "source": "InventoryForecaster",
                    },
                    {
                        "label": "Target Segment",
                        "value": "12,500 newsletter subscribers with bedroom interests",
                        "weight": "primary",
                        "source": "Klaviyo Segmenter",
                    },
                    {
                        "label": "Discount Limit",
                        "value": "15% discount (Allowed range is 10% - 25%)",
                        "weight": "supporting",
                        "source": "MarketingGuardrail",
                    },
                ],
                impact={
                    "financial_impact": 1850.00,  # Expected clearance margin revenue
                    "affected_skus": ["SATEEN-SHEET-WHT-Q", "SATEEN-SHEET-GRY-Q"],
                    "affected_orders": [],
                    "reversible": True,
                    "reversal_window_hours": 2,
                },
            ),
            # 7. Expired Price Adjustment (Low Risk, expired)
            ApprovalAction(
                id="a1b2c3d4-0007-4000-8000-000000000007",
                agent="PricingAgent",
                action_type="price_change",
                status="expired",
                risk_level="low",
                confidence_score=0.90,
                created_at=now - timedelta(hours=25),
                expires_at=now - timedelta(hours=1),
                requires_hitl=True,
                shadow_mode=True,
                payload={
                    "sku": "TSHIRT-BLUE-L",
                    "product_name": "Organic Cotton Crewneck (Blue, Large)",
                    "current_price": 28.00,
                    "proposed_price": 32.00,
                    "change_percent": 14.28,
                    "reasoning": "Strong demand spike (14 orders in last 2 days). Proposing 14% price adjustment to maximize peak sales window.",
                    "competitor_prices": [],
                },
                evidence=[
                    {
                        "label": "Sales Spike",
                        "value": "+250% sales velocity increase over 48h",
                        "weight": "primary",
                        "source": "StoreAnalytics",
                    },
                    {
                        "label": "Inventory Status",
                        "value": "Healthy stock (125 units remaining)",
                        "weight": "supporting",
                        "source": "InventoryForecaster",
                    },
                ],
                impact={
                    "financial_impact": 560.00,
                    "affected_skus": ["TSHIRT-BLUE-L"],
                    "affected_orders": [],
                    "reversible": True,
                    "reversal_window_hours": 168,
                },
            ),
            # 8. Executed Order Hold (High Risk, Approved, executed)
            ApprovalAction(
                id="a1b2c3d4-0008-4000-8000-000000000008",
                agent="FraudAgent",
                action_type="fraud_hold",
                status="executed",
                risk_level="high",
                confidence_score=0.96,
                created_at=now - timedelta(hours=3),
                expires_at=now + timedelta(hours=21),
                requires_hitl=True,
                shadow_mode=True,
                payload={
                    "order_id": "ORD-94710",
                    "customer_name": "John Doe",
                    "customer_email": "john.doe.fraudtest@gmail.com",
                    "order_total": 890.00,
                    "fraud_score": 75,
                    "risk_signals": ["IP country mismatch", "High-frequency card switching"],
                    "recommended_action": "hold",
                },
                evidence=[
                    {
                        "label": "IP Location",
                        "value": "IP: Germany vs Shipping: Los Angeles, CA",
                        "weight": "primary",
                        "source": "IPGeoLocator",
                    },
                    {
                        "label": "Card Count",
                        "value": "3 distinct credit cards attempted within 5 minutes",
                        "weight": "primary",
                        "source": "Stripe Radar",
                    },
                ],
                impact={
                    "financial_impact": 890.00,
                    "affected_skus": ["PHONE-CASE-15PRO"],
                    "affected_orders": ["ORD-94710"],
                    "reversible": True,
                    "reversal_window_hours": 48,
                },
                reviewed_by="admin_operator_1",
                reviewed_at=now - timedelta(hours=2),
                operator_notes="Confirmed IP mismatch with billing company. Order held successfully.",
            ),
        ]

        # Save to DB
        session.add_all(mock_actions)

        # Seed some audit entries to make the audit log look rich
        mock_audit = [
            AuditEntry(
                action_id="a1b2c3d4-0008-4000-8000-000000000008",
                timestamp=now - timedelta(hours=2),
                agent="FraudAgent",
                action_type="fraud_hold",
                decision="approved",
                operator="admin_operator_1",
                confidence_score=0.96,
                financial_impact=890.00,
                details={
                    "notes": "Confirmed IP mismatch with billing company. Order held successfully."
                },
            ),
            AuditEntry(
                action_id=None,
                timestamp=now - timedelta(hours=6),
                agent="ReviewsAgent",
                action_type="review_response",
                decision="auto-approved",
                operator=None,
                confidence_score=0.98,
                financial_impact=0.00,
                details={
                    "review_id": "rev_77102",
                    "rating": 5,
                    "response": "Thank you for your 5-star review! We glad you liked it.",
                },
            ),
            AuditEntry(
                action_id=None,
                timestamp=now - timedelta(hours=10),
                agent="PricingAgent",
                action_type="price_change",
                decision="auto-approved",
                operator=None,
                confidence_score=0.99,
                financial_impact=150.00,
                details={"sku": "MUG-WHITE", "old_price": 12.00, "new_price": 12.20},
            ),
            AuditEntry(
                action_id="a1b2c3d4-0009-4000-8000-000000000009",
                timestamp=now - timedelta(hours=12),
                agent="InventoryAgent",
                action_type="purchase_order",
                decision="rejected",
                operator="admin_operator_1",
                confidence_score=0.74,
                financial_impact=-4500.00,
                details={
                    "reason": "Incorrect recommendation",
                    "notes": "Reorder quantity is too high for this time of year.",
                },
            ),
        ]
        session.add_all(mock_audit)
        await session.commit()
        logger.info("Mock database seeding complete.")
