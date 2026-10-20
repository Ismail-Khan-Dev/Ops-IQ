"""
Abandoned Cart API Routes
Endpoints for cart recovery operations and analytics.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel

from ecommerce_ops.agents.cart_recovery.agent import AbandonedCartAgent
from ecommerce_ops.agents.cart_recovery.discounts import DiscountCodeGenerator
from ecommerce_ops.agents.cart_recovery.models import (
    AbandonedCart,
    CartAnalytics,
    RecoveryStrategy,
)
from ecommerce_ops.agents.cart_recovery.strategy import RecoveryStrategyEngine
from ecommerce_ops.config import settings
from ecommerce_ops.security.auth import require_permission
from ecommerce_ops.security.models import Permission, User
from ecommerce_ops.utils import utc_now

logger = logging.getLogger("ecommerce_ops.api.cart_recovery")

router = APIRouter(prefix="/cart-recovery", tags=["cart-recovery"])

# Singleton agents
_cart_agent = AbandonedCartAgent()
_strategy_engine = RecoveryStrategyEngine()
_discount_generator = DiscountCodeGenerator()


class CartAnalysisRequest(BaseModel):
    cart_id: str
    shop_domain: Optional[str] = None
    items: List[Dict[str, Any]] = []
    total_value: float = 0.0
    customer: Optional[Dict[str, Any]] = None
    checkout_url: Optional[str] = None


class RecoveryActionRequest(BaseModel):
    cart_id: str
    strategy: RecoveryStrategy
    discount_value: float = 0.0
    custom_message: Optional[str] = None


class BatchRecoveryRequest(BaseModel):
    cart_ids: List[str]
    strategy: Optional[RecoveryStrategy] = None
    min_value: float = 0.0


# ── Analysis ───────────────────────────────────────────────


@router.post("/analyze")
async def analyze_cart(
    req: CartAnalysisRequest,
    _: User = Depends(require_permission(Permission.CART_RECOVERY_VIEW)),
):
    """Analyze a single cart and get recovery recommendation."""
    cart_data = {
        "id": req.cart_id,
        "shop_domain": req.shop_domain or settings.SHOPIFY_SHOP_DOMAIN or "unknown",
        "items": req.items,
        "total_value": req.total_value,
        "items_count": len(req.items),
        "status": "abandoned",
        "customer": req.customer,
        "checkout_url": req.checkout_url,
    }

    # Get strategy recommendation
    cart = AbandonedCart(**cart_data)
    recommendation = _strategy_engine.get_strategy_recommendation(cart)

    # Generate discount code if applicable
    code = None
    if recommendation["strategy"] in (
        RecoveryStrategy.DISCOUNT_PERCENT,
        RecoveryStrategy.DISCOUNT_FIXED,
        RecoveryStrategy.FREE_SHIPPING,
    ):
        code = _discount_generator.generate_code(
            cart,
            recommendation["strategy"],
            recommendation["discount_value"],
        )

    return {
        "cart_id": req.cart_id,
        "recommendation": {
            "strategy": recommendation["strategy"].value,
            "risk_level": recommendation["risk_level"].value,
            "discount_value": recommendation["discount_value"],
            "discount_code": code,
            "recovery_probability": round(recommendation["recovery_probability"], 3),
            "estimated_revenue": round(recommendation["estimated_revenue"], 2),
            "reasoning": recommendation["reasoning"],
        },
        "email_context": _discount_generator.get_recovery_email_context(
            cart,
            code or "REC-CODE",
            recommendation["strategy"],
            recommendation["discount_value"],
        ),
    }


@router.post("/analyze/batch")
async def analyze_carts_batch(
    carts: List[CartAnalysisRequest],
    _: User = Depends(require_permission(Permission.CART_RECOVERY_VIEW)),
):
    """Analyze multiple carts in batch."""
    results = []
    for req in carts:
        cart_data = {
            "id": req.cart_id,
            "shop_domain": req.shop_domain or "unknown",
            "items": req.items,
            "total_value": req.total_value,
            "items_count": len(req.items),
            "status": "abandoned",
            "customer": req.customer,
        }
        cart = AbandonedCart(**cart_data)
        recommendation = _strategy_engine.get_strategy_recommendation(cart)
        results.append(
            {
                "cart_id": req.cart_id,
                "strategy": recommendation["strategy"].value,
                "risk_level": recommendation["risk_level"].value,
                "recovery_probability": round(recommendation["recovery_probability"], 3),
                "estimated_revenue": round(recommendation["estimated_revenue"], 2),
            }
        )

    # Aggregate stats
    total_value = sum(r.total_value for r in carts)
    total_potential = sum(r["estimated_revenue"] for r in results)

    return {
        "analyzed": len(results),
        "total_value": round(total_value, 2),
        "total_potential_revenue": round(total_potential, 2),
        "results": results,
    }


# ── Recovery Actions ───────────────────────────────────────


@router.post("/recover")
async def trigger_recovery(
    req: RecoveryActionRequest,
    background_tasks: BackgroundTasks,
    _: User = Depends(require_permission(Permission.CART_RECOVERY_EXECUTE)),
):
    """Trigger recovery for a single cart."""
    # Generate discount code
    code = _discount_generator.generate_simple()

    # In production, this would:
    # 1. Create Shopify discount code
    # 2. Send recovery email
    # 3. Track email events

    background_tasks.add_task(
        _execute_recovery,
        cart_id=req.cart_id,
        strategy=req.strategy,
        discount_code=code,
        discount_value=req.discount_value,
    )

    return {
        "status": "recovery_initiated",
        "cart_id": req.cart_id,
        "strategy": req.strategy.value,
        "discount_code": code,
        "message": "Recovery campaign started",
    }


@router.post("/recover/batch")
async def trigger_batch_recovery(
    req: BatchRecoveryRequest,
    background_tasks: BackgroundTasks,
    _: User = Depends(require_permission(Permission.CART_RECOVERY_EXECUTE)),
):
    """Trigger recovery for multiple carts."""
    results = []
    for cart_id in req.cart_ids:
        code = _discount_generator.generate_simple()
        background_tasks.add_task(
            _execute_recovery,
            cart_id=cart_id,
            strategy=req.strategy or RecoveryStrategy.DISCOUNT_PERCENT,
            discount_code=code,
            discount_value=req.min_value,
        )
        results.append(
            {
                "cart_id": cart_id,
                "discount_code": code,
                "status": "initiated",
            }
        )

    return {
        "status": "batch_recovery_initiated",
        "count": len(results),
        "results": results,
    }


# ── Analytics ──────────────────────────────────────────────


@router.get("/analytics")
async def get_cart_analytics(
    days: int = Query(7, ge=1, le=90),
    _: User = Depends(require_permission(Permission.CART_RECOVERY_VIEW)),
):
    """Get cart recovery analytics."""
    # In production, this would query the database
    # For now, return sample analytics
    return CartAnalytics(
        total_abandoned=127,
        total_recovered=43,
        recovery_rate=33.9,
        total_revenue_lost=15420.50,
        total_revenue_recovered=5230.75,
        average_cart_value=121.42,
        average_recovery_time_hours=18.5,
        top_recovery_strategy=RecoveryStrategy.DISCOUNT_PERCENT,
        strategy_breakdown={
            "discount_percent": {"count": 25, "recovered": 12, "revenue": 3100.00},
            "discount_fixed": {"count": 40, "recovered": 15, "revenue": 1800.00},
            "free_shipping": {"count": 35, "recovered": 10, "revenue": 850.00},
            "urgency": {"count": 15, "recovered": 4, "revenue": 320.00},
            "social_proof": {"count": 12, "recovered": 2, "revenue": 160.75},
        },
        risk_distribution={
            "low": 45,
            "medium": 52,
            "high": 25,
            "critical": 5,
        },
    )


@router.get("/analytics/strategies")
async def get_strategy_analytics(
    _: User = Depends(require_permission(Permission.CART_RECOVERY_VIEW)),
):
    """Get strategy effectiveness analytics."""
    return {
        "strategies": [
            {
                "name": "discount_percent",
                "display_name": "Percentage Discount",
                "avg_discount": 12.5,
                "conversion_rate": 0.34,
                "avg_revenue": 89.50,
                "recommended_for": "High-value carts, VIP customers",
            },
            {
                "name": "discount_fixed",
                "display_name": "Fixed Amount Discount",
                "avg_discount": 8.0,
                "conversion_rate": 0.28,
                "avg_revenue": 65.20,
                "recommended_for": "Medium-value carts, repeat customers",
            },
            {
                "name": "free_shipping",
                "display_name": "Free Shipping",
                "avg_discount": 0,
                "conversion_rate": 0.22,
                "avg_revenue": 45.80,
                "recommended_for": "All cart values, shipping-sensitive customers",
            },
            {
                "name": "urgency",
                "display_name": "Urgency messaging",
                "avg_discount": 0,
                "conversion_rate": 0.15,
                "avg_revenue": 35.00,
                "recommended_for": "Low-value carts, time-sensitive items",
            },
        ],
        "best_practices": [
            "Send first recovery email within 1 hour of abandonment",
            "Follow up with second email at 24 hours",
            "Final reminder at 72 hours with stronger discount",
            "Segment customers by LTV for personalized offers",
            "A/B test subject lines and discount levels",
        ],
    }


@router.get("/health")
async def cart_recovery_health():
    """Health check for cart recovery service."""
    return {
        "status": "healthy",
        "agent": "AbandonedCartAgent",
        "strategy_engine": "RecoveryStrategyEngine",
        "discount_generator": "DiscountCodeGenerator",
        "timestamp": utc_now().isoformat(),
    }


# ── Background Tasks ───────────────────────────────────────


async def _execute_recovery(
    cart_id: str,
    strategy: RecoveryStrategy,
    discount_code: str,
    discount_value: float,
):
    """Execute recovery campaign in background."""
    try:
        logger.info(
            "Executing recovery for cart %s: strategy=%s code=%s",
            cart_id,
            strategy.value,
            discount_code,
        )

        # In production:
        # 1. Create Shopify price rule + discount code
        # 2. Send email via Resend/SES
        # 3. Store recovery record
        # 4. Schedule follow-ups

        logger.info("Recovery campaign completed for cart %s", cart_id)

    except Exception as e:
        logger.error("Recovery failed for cart %s: %s", cart_id, e)
