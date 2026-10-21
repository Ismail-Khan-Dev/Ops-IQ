"""
Marketing & Ad-Spend Bleed Stopper API Routes.
Provides endpoints for synchronizing real-time Shopify inventory with Meta/TikTok ad sets,
pausing ads on sold-out products, and tracking preserved ad spend.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from ecommerce_ops.connectors.meta import MetaAdsClient
from ecommerce_ops.marketing.ad_spend_guardian import AdSpendGuardian
from ecommerce_ops.models import ShopifyProductSnapshot, async_session_factory
from ecommerce_ops.security.auth import require_permission
from ecommerce_ops.security.models import Permission, User

logger = logging.getLogger("ecommerce_ops.api.marketing")

router = APIRouter(prefix="/marketing", tags=["marketing"])


class InventoryItemPayload(BaseModel):
    sku: str
    inventory_quantity: int = 0
    title: Optional[str] = None


class SyncInventoryToAdsRequest(BaseModel):
    items: Optional[List[InventoryItemPayload]] = Field(
        None, description="List of inventory items. If empty, automatically pulls from DB snapshots."
    )
    oos_threshold: int = Field(0, ge=0, description="Out of stock threshold (default: 0)")
    auto_execute: bool = Field(True, description="Whether to execute live ad set status changes")


class AdSetActionRequest(BaseModel):
    adset_id: str = Field(..., description="Meta Ad Set ID")


@router.post("/meta/sync-inventory")
async def sync_inventory_with_meta_ads(
    req: SyncInventoryToAdsRequest,
    _: User = Depends(require_permission(Permission.SHOPIFY_CONFIGURE)),
):
    """Scan inventory stock against running Meta ad sets.

    Pauses ads for sold-out items to stop burning ad budget.
    """
    inventory_data: List[Dict[str, Any]] = []

    if req.items:
        inventory_data = [item.model_dump() for item in req.items]
    else:
        # Pull live product snapshots from DB
        async with async_session_factory() as session:
            res = await session.execute(select(ShopifyProductSnapshot))
            snapshots = res.scalars().all()
            for s in snapshots:
                inventory_data.append({
                    "sku": s.sku or "",
                    "inventory_quantity": s.total_inventory,
                    "title": s.title or "",
                })

    guardian = AdSpendGuardian()
    try:
        report = await guardian.sync_inventory_to_ads(
            inventory_items=inventory_data,
            oos_threshold=req.oos_threshold,
            auto_execute=req.auto_execute,
        )
        return report
    except Exception as e:
        logger.error("Failed to sync inventory to Meta ads: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ad-spend guardian sync error: {str(e)}",
        )


@router.get("/meta/saved-spend")
async def get_ad_spend_saved_metrics(
    _: User = Depends(require_permission(Permission.OBSERVABILITY_VIEW)),
):
    """Retrieve cumulative and daily preserved ad spend metrics."""
    guardian = AdSpendGuardian()
    return guardian.get_ad_spend_saved_summary()


@router.post("/meta/pause-adset")
async def pause_adset_manually(
    req: AdSetActionRequest,
    _: User = Depends(require_permission(Permission.SHOPIFY_CONFIGURE)),
):
    """Manually pause an ad set immediately."""
    client = MetaAdsClient()
    try:
        return await client.pause_adset(req.adset_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to pause ad set: {str(e)}",
        )


@router.post("/meta/unpause-adset")
async def unpause_adset_manually(
    req: AdSetActionRequest,
    _: User = Depends(require_permission(Permission.SHOPIFY_CONFIGURE)),
):
    """Manually reactivate an ad set."""
    client = MetaAdsClient()
    try:
        return await client.unpause_adset(req.adset_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to unpause ad set: {str(e)}",
        )
