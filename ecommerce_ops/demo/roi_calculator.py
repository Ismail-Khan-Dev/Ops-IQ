"""
ROI Calculator Engine
Calculates Return on Investment for e-commerce operations automation.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ecommerce_ops.utils import utc_now

logger = logging.getLogger("ecommerce_ops.roi")


@dataclass
class CostBreakdown:
    """Cost breakdown for a specific area."""

    labor_hours_saved: float = 0.0
    labor_cost_per_hour: float = 25.0
    tools_cost_monthly: float = 0.0
    infrastructure_cost_monthly: float = 0.0
    implementation_cost: float = 0.0
    training_cost: float = 0.0

    @property
    def total_monthly_cost(self) -> float:
        return self.tools_cost_monthly + self.infrastructure_cost_monthly

    @property
    def labor_savings_monthly(self) -> float:
        return self.labor_hours_saved * self.labor_cost_per_hour * 30

    @property
    def total_investment(self) -> float:
        return self.implementation_cost + self.training_cost + (self.total_monthly_cost * 12)


@dataclass
class SavingsEstimate:
    """Savings estimate for a specific use case."""

    area: str
    description: str
    labor_hours_saved_per_month: float
    error_reduction_percent: float
    revenue_increase_percent: float
    cost_per_month: float
    savings_per_month: float
    roi_percent: float


@dataclass
class ROIReport:
    """Complete ROI report."""

    generated_at: str
    period_months: int
    total_investment: float
    total_savings: float
    net_benefit: float
    roi_percent: float
    payback_period_months: float
    breakdowns: List[SavingsEstimate] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)


class ROICalculator:
    """Calculate ROI for e-commerce automation."""

    def __init__(self):
        self.hourly_labor_rate = 25.0
        self.monthly_tool_cost = 500.0
        self.monthly_infra_cost = 200.0
        self.one_time_setup_cost = 5000.0

        self.use_cases = {
            "fraud_detection": {
                "area": "Fraud Detection",
                "description": "Automated fraud detection and prevention",
                "labor_hours_saved": 80,
                "error_reduction": 95,
                "revenue_increase": 5,
                "monthly_cost": 150,
            },
            "inventory_management": {
                "area": "Inventory Management",
                "description": "AI-powered inventory optimization",
                "labor_hours_saved": 60,
                "error_reduction": 85,
                "revenue_increase": 8,
                "monthly_cost": 120,
            },
            "price_optimization": {
                "area": "Price Optimization",
                "description": "Dynamic pricing engine",
                "labor_hours_saved": 40,
                "error_reduction": 70,
                "revenue_increase": 12,
                "monthly_cost": 100,
            },
            "review_moderation": {
                "area": "Review Moderation",
                "description": "Automated review analysis and moderation",
                "labor_hours_saved": 30,
                "error_reduction": 90,
                "revenue_increase": 3,
                "monthly_cost": 80,
            },
            "marketing_automation": {
                "area": "Marketing Automation",
                "description": "AI-driven marketing campaigns",
                "labor_hours_saved": 50,
                "error_reduction": 75,
                "revenue_increase": 10,
                "monthly_cost": 130,
            },
            "abandoned_cart_recovery": {
                "area": "Abandoned Cart Recovery",
                "description": "Intelligent cart recovery system",
                "labor_hours_saved": 35,
                "error_reduction": 60,
                "revenue_increase": 15,
                "monthly_cost": 90,
            },
            "customer_support": {
                "area": "Customer Support",
                "description": "AI-powered customer support agent",
                "labor_hours_saved": 100,
                "error_reduction": 80,
                "revenue_increase": 6,
                "monthly_cost": 180,
            },
        }

    def calculate_roi(
        self,
        active_use_cases: Optional[List[str]] = None,
        monthly_revenue: float = 100000.0,
        period_months: int = 12,
    ) -> ROIReport:
        """Calculate ROI for selected use cases."""
        if active_use_cases is None:
            active_use_cases = list(self.use_cases.keys())

        breakdowns = []
        total_labor_hours = 0
        total_monthly_cost = 0
        total_savings = 0

        for uc_key in active_use_cases:
            if uc_key not in self.use_cases:
                continue

            uc = self.use_cases[uc_key]
            labor_savings = uc["labor_hours_saved"] * self.hourly_labor_rate * 30
            revenue_increase = monthly_revenue * (uc["revenue_increase"] / 100)
            error_savings = labor_savings * (uc["error_reduction"] / 100)
            total_uc_savings = labor_savings + revenue_increase + error_savings
            net_uc_savings = total_uc_savings - uc["monthly_cost"]
            roi = (net_uc_savings / uc["monthly_cost"] * 100) if uc["monthly_cost"] > 0 else 0

            breakdown = SavingsEstimate(
                area=uc["area"],
                description=uc["description"],
                labor_hours_saved_per_month=uc["labor_hours_saved"],
                error_reduction_percent=uc["error_reduction"],
                revenue_increase_percent=uc["revenue_increase"],
                cost_per_month=uc["monthly_cost"],
                savings_per_month=round(total_uc_savings, 2),
                roi_percent=round(roi, 1),
            )
            breakdowns.append(breakdown)

            total_labor_hours += uc["labor_hours_saved"]
            total_monthly_cost += uc["monthly_cost"]
            total_savings += total_uc_savings

        total_investment = self.one_time_setup_cost + (total_monthly_cost * period_months)
        total_savings_period = total_savings * period_months
        net_benefit = total_savings_period - total_investment
        roi_pct = (net_benefit / total_investment * 100) if total_investment > 0 else 0
        payback = (total_investment / total_savings) if total_savings > 0 else float("inf")

        report = ROIReport(
            generated_at=utc_now().isoformat(),
            period_months=period_months,
            total_investment=round(total_investment, 2),
            total_savings=round(total_savings_period, 2),
            net_benefit=round(net_benefit, 2),
            roi_percent=round(roi_pct, 1),
            payback_period_months=round(payback, 1),
            breakdowns=breakdowns,
            recommendations=self._generate_recommendations(breakdowns, roi_pct),
            summary={
                "active_use_cases": len(active_use_cases),
                "total_labor_hours_saved_monthly": total_labor_hours,
                "monthly_cost": total_monthly_cost,
                "monthly_savings": round(total_savings, 2),
                "labor_cost_per_hour": self.hourly_labor_rate,
                "monthly_revenue": monthly_revenue,
            },
        )

        return report

    def _generate_recommendations(
        self, breakdowns: List[SavingsEstimate], roi_pct: float
    ) -> List[str]:
        """Generate recommendations based on ROI analysis."""
        recommendations = []

        if roi_pct > 200:
            recommendations.append(
                "Excellent ROI! Consider scaling implementation to all use cases."
            )
        elif roi_pct > 100:
            recommendations.append("Good ROI. Focus on high-impact use cases first.")
        elif roi_pct > 50:
            recommendations.append(
                "Moderate ROI. Consider optimizing costs or increasing adoption."
            )
        else:
            recommendations.append("Low ROI. Review implementation strategy and cost structure.")

        if breakdowns:
            best = max(breakdowns, key=lambda x: x.roi_percent)
            recommendations.append(
                f"Highest ROI use case: {best.area} ({best.roi_percent}%). "
                f"Prioritize this for maximum impact."
            )

            worst = min(breakdowns, key=lambda x: x.roi_percent)
            if worst.roi_percent < 50:
                recommendations.append(
                    f"Consider reviewing {worst.area} ({worst.roi_percent}% ROI) "
                    f"for cost optimization opportunities."
                )

        total_hours = sum(b.labor_hours_saved_per_month for b in breakdowns)
        if total_hours > 200:
            recommendations.append(
                f"Saving {total_hours:.0f} labor hours/month. "
                f"Redeploy staff to high-value strategic work."
            )

        recommendations.append(
            "Implement monitoring dashboards to track actual vs projected savings."
        )

        return recommendations

    def get_quick_estimate(self, monthly_revenue: float = 100000.0) -> Dict:
        """Quick ROI estimate for all use cases."""
        report = self.calculate_roi(monthly_revenue=monthly_revenue)
        return {
            "monthly_savings": report.summary["monthly_savings"],
            "annual_savings": report.total_savings,
            "roi_percent": report.roi_percent,
            "payback_months": report.payback_period_months,
            "labor_hours_saved_monthly": report.summary["total_labor_hours_saved_monthly"],
        }
