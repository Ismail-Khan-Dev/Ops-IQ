"""
Pilot Onboarding & Shopify App Store Billing API Routes
Provides endpoints for onboarding US DTC pilot brands, verifying App Store pre-flight readiness,
managing App Bridge embedded billing charges, and tracking pilot cohort metrics.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from ecommerce_ops.connectors.shopify.billing import (
    SHOPIFY_SUBSCRIPTION_PLANS,
    ShopifyBillingManager,
)
from ecommerce_ops.connectors.shopify.onboarding import PilotOnboardingEngine
from ecommerce_ops.security.auth import require_permission
from ecommerce_ops.security.models import Permission, User

logger = logging.getLogger("ecommerce_ops.api.onboarding")

router = APIRouter(tags=["onboarding", "billing"])


# ── Pydantic Request & Response Schemas ─────────────────────────────────────


class PilotProvisionRequest(BaseModel):
    shop_domain: str = Field(..., description="Target Shopify shop domain (e.g. brand.myshopify.com)")
    access_token: Optional[str] = Field(None, description="Offline access token if pre-authorized")
    scope: Optional[str] = Field(None, description="Granted OAuth scopes")
    plan_tier: str = Field("growth", description="Pilot subscription tier: starter, growth, or enterprise")
    shadow_mode: bool = Field(True, description="Enable shadow mode safety guardrail (no live interventions)")
    auto_sync: bool = Field(False, description="Trigger catalog and order sync upon onboarding")


class PilotSettingsUpdateRequest(BaseModel):
    shadow_mode: Optional[bool] = Field(None, description="Enable or disable shadow dry-run mode")
    fraud_threshold: Optional[int] = Field(None, ge=1, le=100, description="Risk threshold for 3PL holds")


class CreateChargeRequest(BaseModel):
    shop_domain: str = Field(..., description="Shop domain to bill")
    plan_tier: str = Field("growth", description="Plan: starter, growth, or enterprise")
    return_url: Optional[str] = Field(None, description="Merchant redirect URL after accepting charge")
    test_mode: Optional[bool] = Field(None, description="Whether to bill in Shopify test mode (free)")


# ── Pilot Onboarding Endpoints ──────────────────────────────────────────────


@router.post("/onboarding/provision")
async def provision_pilot_store(
    req: PilotProvisionRequest,
    _: User = Depends(require_permission(Permission.SHOPIFY_CONFIGURE)),
):
    """Provision a new pilot merchant with default safety guardrails,

    tier subscription, and pre-flight readiness verification.
    """
    try:
        result = await PilotOnboardingEngine.provision_pilot_merchant(
            shop_domain=req.shop_domain,
            access_token=req.access_token,
            scope=req.scope,
            plan_tier=req.plan_tier,
            shadow_mode=req.shadow_mode,
            auto_sync=req.auto_sync,
        )
        return result
    except Exception as e:
        logger.error("Failed to provision pilot store %s: %s", req.shop_domain, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Provisioning error: {str(e)}",
        )


@router.get("/onboarding/readiness")
async def check_store_readiness(
    shop: str = Query(..., description="Shopify store domain to verify"),
    _: User = Depends(require_permission(Permission.SHOPIFY_CONFIGURE)),
):
    """Run pre-flight readiness audit for a merchant store.

    Evaluates OAuth credentials, scopes, 3PL hold compatibility,
    webhook compliance, and catalog sync state.
    """
    try:
        report = await PilotOnboardingEngine.verify_store_readiness(shop_domain=shop)
        return report
    except Exception as e:
        logger.error("Readiness check error for %s: %s", shop, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Readiness check failed: {str(e)}",
        )


@router.get("/onboarding/cohort")
async def get_pilot_cohort(
    _: User = Depends(require_permission(Permission.OBSERVABILITY_VIEW)),
):
    """Retrieve multi-store pilot cohort dashboard metrics (5-store target,

    active stores, aggregate sync counts, and readiness distribution).
    """
    return await PilotOnboardingEngine.get_pilot_cohort_summary()


@router.patch("/onboarding/settings")
async def update_pilot_settings(
    req: PilotSettingsUpdateRequest,
    _: User = Depends(require_permission(Permission.SHOPIFY_CONFIGURE)),
):
    """Update global pilot guardrails (shadow mode toggle, fraud threshold)."""
    return await PilotOnboardingEngine.update_pilot_settings(
        shadow_mode=req.shadow_mode,
        fraud_threshold=req.fraud_threshold,
    )


# ── Shopify Billing Endpoints ───────────────────────────────────────────────


@router.get("/billing/plans")
async def list_billing_plans():
    """List available Shopify App subscription plans and limits."""
    return {
        "plans": SHOPIFY_SUBSCRIPTION_PLANS,
        "trial_days": 14,
        "currency": "USD",
    }


@router.post("/billing/create-charge")
async def create_billing_charge(
    req: CreateChargeRequest,
    _: User = Depends(require_permission(Permission.SHOPIFY_CONFIGURE)),
):
    """Create a recurring subscription application charge with a 14-day trial."""
    try:
        billing_mgr = await ShopifyBillingManager.for_shop(req.shop_domain)
        result = await billing_mgr.create_recurring_charge(
            plan_tier=req.plan_tier,
            return_url=req.return_url,
            test_mode=req.test_mode,
        )
        return result
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as e:
        logger.error("Billing charge creation failed for %s: %s", req.shop_domain, e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Shopify Billing API error: {str(e)}",
        )


@router.get("/billing/callback")
async def billing_callback(
    shop: str = Query(..., description="Store domain"),
    charge_id: str = Query(..., description="Shopify recurring application charge ID"),
):
    """Shopify redirects merchant here after approving charge.

    Activates the recurring charge.
    """
    try:
        billing_mgr = await ShopifyBillingManager.for_shop(shop)
        activation = await billing_mgr.activate_charge(charge_id=charge_id)
        return {
            "status": "success",
            "shop": shop,
            "charge_id": charge_id,
            "activation": activation,
            "message": "Subscription active! Your 14-day free trial has commenced.",
        }
    except Exception as e:
        logger.error("Billing callback activation failed for %s (charge %s): %s", shop, charge_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Activation error: {str(e)}",
        )


@router.get("/billing/status")
async def get_billing_status(
    shop: str = Query(..., description="Shop domain"),
    _: User = Depends(require_permission(Permission.OBSERVABILITY_VIEW)),
):
    """Check active recurring subscription status for a store."""
    try:
        billing_mgr = await ShopifyBillingManager.for_shop(shop)
        status_info = await billing_mgr.get_active_subscription()
        return {
            "shop": shop,
            **status_info,
        }
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as e:
        logger.error("Failed to query billing status for %s: %s", shop, e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Billing query error: {str(e)}",
        )
