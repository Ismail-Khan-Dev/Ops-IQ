"""
Demo and ROI API Routes
Endpoints for demo environment and ROI calculations.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ecommerce_ops.demo.roi_calculator import ROICalculator
from ecommerce_ops.security.auth import require_admin, require_auth, require_permission
from ecommerce_ops.security.models import Permission, User

logger = logging.getLogger("ecommerce_ops.api.demo")

router = APIRouter(prefix="/demo", tags=["demo"])

roi_calculator = ROICalculator()


class ROIRequest(BaseModel):
    active_use_cases: Optional[List[str]] = None
    monthly_revenue: float = 100000.0
    period_months: int = 12


class QuickEstimateRequest(BaseModel):
    monthly_revenue: float = 100000.0


# ── ROI Calculator ─────────────────────────────────────────


@router.post("/roi/calculate")
async def calculate_roi(
    req: ROIRequest,
    _: User = Depends(require_permission(Permission.DASHBOARD_VIEW)),
):
    """Calculate ROI for selected use cases."""
    report = roi_calculator.calculate_roi(
        active_use_cases=req.active_use_cases,
        monthly_revenue=req.monthly_revenue,
        period_months=req.period_months,
    )

    return {
        "generated_at": report.generated_at,
        "period_months": report.period_months,
        "total_investment": report.total_investment,
        "total_savings": report.total_savings,
        "net_benefit": report.net_benefit,
        "roi_percent": report.roi_percent,
        "payback_period_months": report.payback_period_months,
        "summary": report.summary,
        "breakdowns": [
            {
                "area": b.area,
                "description": b.description,
                "labor_hours_saved_per_month": b.labor_hours_saved_per_month,
                "error_reduction_percent": b.error_reduction_percent,
                "revenue_increase_percent": b.revenue_increase_percent,
                "cost_per_month": b.cost_per_month,
                "savings_per_month": b.savings_per_month,
                "roi_percent": b.roi_percent,
            }
            for b in report.breakdowns
        ],
        "recommendations": report.recommendations,
    }


@router.post("/roi/quick-estimate")
async def quick_estimate(
    req: QuickEstimateRequest,
    _: User = Depends(require_permission(Permission.DASHBOARD_VIEW)),
):
    """Quick ROI estimate for all use cases."""
    estimate = roi_calculator.get_quick_estimate(monthly_revenue=req.monthly_revenue)
    return estimate


@router.get("/roi/use-cases")
async def list_use_cases(_: User = Depends(require_permission(Permission.DASHBOARD_VIEW))):
    """List all available use cases."""
    return {
        "use_cases": [
            {
                "key": key,
                "area": uc["area"],
                "description": uc["description"],
                "labor_hours_saved": uc["labor_hours_saved"],
                "error_reduction_percent": uc["error_reduction"],
                "revenue_increase_percent": uc["revenue_increase"],
                "monthly_cost": uc["monthly_cost"],
            }
            for key, uc in roi_calculator.use_cases.items()
        ],
    }


# ── Demo Environment ───────────────────────────────────────


@router.get("/demo/status")
async def demo_status(_: User = Depends(require_permission(Permission.DASHBOARD_VIEW))):
    """Get demo environment status."""
    import os

    is_demo = os.getenv("DEMO_MODE", "false").lower() == "true"
    return {
        "demo_mode": is_demo,
        "environment": os.getenv("ENV", "development"),
        "features": {
            "fraud_detection": True,
            "inventory_management": True,
            "price_optimization": True,
            "review_moderation": True,
            "marketing_automation": True,
            "abandoned_cart_recovery": True,
            "customer_support": True,
            "shopify_integration": True,
            "vector_memory": True,
            "rbac_security": True,
        },
    }


@router.get("/demo/scenarios")
async def demo_scenarios(_: User = Depends(require_permission(Permission.DASHBOARD_VIEW))):
    """List demo scenarios."""
    return {
        "scenarios": [
            {
                "id": "fraud_detection",
                "name": "Fraud Detection",
                "description": "Detect fraudulent orders in real-time",
                "steps": [
                    "New order received from Shopify",
                    "Agent analyzes order patterns",
                    "Risk score calculated",
                    "Decision: approve/flag/reject",
                ],
                "expected_savings": "$5,000/month",
            },
            {
                "id": "cart_recovery",
                "name": "Abandoned Cart Recovery",
                "description": "Recover abandoned carts with AI",
                "steps": [
                    "Cart abandoned detected",
                    "Recovery strategy selected",
                    "Discount code generated",
                    "Email/SMS sent",
                ],
                "expected_savings": "$8,000/month",
            },
            {
                "id": "price_optimization",
                "name": "Dynamic Pricing",
                "description": "Optimize prices based on demand",
                "steps": [
                    "Market data collected",
                    "Competitor prices analyzed",
                    "Demand elasticity calculated",
                    "Price updated",
                ],
                "expected_savings": "$12,000/month",
            },
            {
                "id": "customer_support",
                "name": "Customer Support",
                "description": "AI-powered customer support",
                "steps": [
                    "Customer ticket received",
                    "Intent and sentiment analyzed",
                    "Response generated",
                    "Ticket routed to agent if needed",
                ],
                "expected_savings": "$10,000/month",
            },
        ],
    }


@router.post("/demo/run/{scenario_id}")
async def run_demo_scenario(
    scenario_id: str,
    user: dict = Depends(require_auth),
):
    """Run a demo scenario."""
    scenarios = {
        "fraud_detection": {
            "status": "completed",
            "result": {
                "order_id": "DEMO-001",
                "risk_score": 0.85,
                "decision": "flagged",
                "reason": "High-risk shipping address",
                "processing_time_ms": 1250,
            },
        },
        "cart_recovery": {
            "status": "completed",
            "result": {
                "cart_id": "CART-001",
                "recovery_strategy": "discount_10_percent",
                "discount_code": "SAVE10-DEMO",
                "email_sent": True,
                "estimated_recovery_rate": "15%",
            },
        },
        "price_optimization": {
            "status": "completed",
            "result": {
                "product_id": "PROD-001",
                "current_price": 49.99,
                "optimized_price": 44.99,
                "expected_volume_increase": "20%",
                "expected_revenue_increase": "12%",
            },
        },
        "customer_support": {
            "status": "completed",
            "result": {
                "ticket_id": "TICKET-001",
                "sentiment": "negative",
                "category": "billing",
                "priority": "high",
                "auto_response_generated": True,
                "escalated_to_human": False,
            },
        },
    }

    if scenario_id not in scenarios:
        raise HTTPException(status_code=404, detail="Scenario not found")

    return scenarios[scenario_id]


@router.post("/demo/seed")
async def seed_demo_data(user: User = Depends(require_admin)):
    """Seed the database with expanded demo data for a rich dashboard."""
    from ecommerce_ops.demo.seed_data import seed_expanded_demo

    result = await seed_expanded_demo()
    return result
