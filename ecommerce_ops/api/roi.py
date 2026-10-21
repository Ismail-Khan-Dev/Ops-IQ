"""
ROI & Margin Preservation Analytics API
Endpoints for tracking preserved GMV, reverse logistics avoidance savings,
net margin ROI, and real-time return/swap unit economics evaluations.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from ecommerce_ops.analytics.margin_preservation import MarginPreservationCalculator
from ecommerce_ops.models import ApprovalAction, async_session_factory
from ecommerce_ops.returns.live_margin_widget import LiveMarginWidget
from ecommerce_ops.returns.up_exchange import UpExchangeEngine
from ecommerce_ops.returns.wardrobing_shield import WardrobingShield
from ecommerce_ops.security.auth import require_permission
from ecommerce_ops.security.models import Permission, User

logger = logging.getLogger("ecommerce_ops.api.roi")

router = APIRouter(prefix="/roi", tags=["roi"])


class ReturnEvaluationRequest(BaseModel):
    item_price: float = Field(..., gt=0.0, description="MSRP or selling price of the item")
    cogs: Optional[float] = Field(None, ge=0.0, description="Cost of goods sold (optional, default 28%)")
    category: str = Field("apparel", description="Product category (apparel, beauty, shoes, home, etc.)")
    return_reason: str = Field("sizing_fit", description="Customer reason (sizing_fit, defective, changed_mind)")
    customer_is_vip: bool = Field(False, description="Whether customer is repeat/high LTV shopper")


class SwapEvaluationRequest(BaseModel):
    original_price: float = Field(..., gt=0.0, description="Price of out-of-stock original item")
    swap_price: float = Field(..., gt=0.0, description="Price of proposed substitution item")
    original_cogs: Optional[float] = Field(None, ge=0.0)
    swap_cogs: Optional[float] = Field(None, ge=0.0)


class WardrobingEvaluationRequest(BaseModel):
    order: Dict[str, Any] = Field(..., description="Order payload containing line items")
    historical_return_rate: Optional[float] = Field(None, ge=0.0, le=1.0)
    previous_returns_count: int = Field(0, ge=0)


class UpExchangeRequest(BaseModel):
    item_price: float = Field(..., gt=0.0, description="MSRP of returning item")
    title: str = Field("Purchased Item", description="Product title")
    category: str = Field("apparel", description="Product category")
    return_reason: str = Field("sizing_fit", description="Customer reason for return")


@router.get("/margin-preservation")
async def get_margin_preservation_summary(
    _: User = Depends(require_permission(Permission.OBSERVABILITY_VIEW)),
):
    """Get aggregated merchant ROI, preserved GMV, and reverse logistics savings."""
    async with async_session_factory() as session:
        res = await session.execute(
            select(ApprovalAction).where(ApprovalAction.status.in_(("executed", "approved")))
        )
        actions = res.scalars().all()

    calculator = MarginPreservationCalculator()
    summary = calculator.aggregate_margin_metrics(actions)
    return summary


@router.post("/returns/evaluate")
async def evaluate_return_strategy(
    req: ReturnEvaluationRequest,
    _: User = Depends(require_permission(Permission.OBSERVABILITY_VIEW)),
):
    """Evaluate return unit economics and return optimal margin-preserving strategy."""
    calculator = MarginPreservationCalculator()
    return calculator.evaluate_return_unit_economics(
        item_price=req.item_price,
        cogs=req.cogs,
        category=req.category,
        return_reason=req.return_reason,
        customer_is_vip=req.customer_is_vip,
    )


@router.post("/swaps/evaluate")
async def evaluate_swap_economics(
    req: SwapEvaluationRequest,
    _: User = Depends(require_permission(Permission.OBSERVABILITY_VIEW)),
):
    """Evaluate unit economics of an out-of-stock item substitution."""
    calculator = MarginPreservationCalculator()
    return calculator.evaluate_order_swap_unit_economics(
        original_price=req.original_price,
        swap_price=req.swap_price,
        original_cogs=req.original_cogs,
        swap_cogs=req.swap_cogs,
    )


@router.post("/wardrobing/evaluate")
async def evaluate_wardrobing_risk(
    req: WardrobingEvaluationRequest,
    _: User = Depends(require_permission(Permission.OBSERVABILITY_VIEW)),
):
    """Detect order bracketing / multi-size purchasing patterns."""
    return WardrobingShield.detect_bracketing(
        order=req.order,
        historical_return_rate=req.historical_return_rate,
        previous_returns_count=req.previous_returns_count,
    )


@router.post("/up-exchange/negotiate")
async def generate_up_exchange(
    req: UpExchangeRequest,
    _: User = Depends(require_permission(Permission.OBSERVABILITY_VIEW)),
):
    """Generate high-converting Keep-It Sweetener and Tier-Up Upgrade offers before cash refund."""
    return UpExchangeEngine.generate_up_exchange_offers(
        item_price=req.item_price,
        title=req.title,
        category=req.category,
        return_reason=req.return_reason,
    )


@router.get("/live-widget")
async def get_live_margin_widget(
    _: User = Depends(require_permission(Permission.OBSERVABILITY_VIEW)),
):
    """Fetch live preserved margin metrics and embeddable Shopify Admin badge."""
    return await LiveMarginWidget.get_live_margin_summary()
