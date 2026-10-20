"""Tests for demo/ module (roi_calculator, helpers, seed_data)."""
from ecommerce_ops.demo.helpers import (
    generate_demo_analytics,
    generate_demo_cart,
    generate_demo_order,
    generate_demo_product,
    generate_demo_ticket,
)
from ecommerce_ops.demo.roi_calculator import CostBreakdown, ROICalculator, ROIReport

# ── ROICalculator tests ────────────────────────────────────


class TestCostBreakdown:
    def test_total_monthly_cost(self):
        cb = CostBreakdown(tools_cost_monthly=100, infrastructure_cost_monthly=50)
        assert cb.total_monthly_cost == 150

    def test_labor_savings_monthly(self):
        cb = CostBreakdown(labor_hours_saved=10, labor_cost_per_hour=25)
        assert cb.labor_savings_monthly == 7500

    def test_total_investment(self):
        cb = CostBreakdown(
            implementation_cost=1000, training_cost=500,
            tools_cost_monthly=100, infrastructure_cost_monthly=50,
        )
        assert cb.total_investment == 1000 + 500 + (150 * 12)


class TestROICalculator:
    def setup_method(self):
        self.calc = ROICalculator()

    def test_calculate_roi_all_use_cases(self):
        report = self.calc.calculate_roi()
        assert isinstance(report, ROIReport)
        assert len(report.breakdowns) == 7
        assert report.period_months == 12
        assert report.total_investment > 0
        assert report.total_savings > 0

    def test_calculate_roi_specific_use_cases(self):
        report = self.calc.calculate_roi(active_use_cases=["fraud_detection"])
        assert len(report.breakdowns) == 1
        assert report.breakdowns[0].area == "Fraud Detection"

    def test_calculate_roi_invalid_use_case_ignored(self):
        report = self.calc.calculate_roi(active_use_cases=["nonexistent"])
        assert len(report.breakdowns) == 0

    def test_calculate_roi_custom_revenue(self):
        report = self.calc.calculate_roi(monthly_revenue=500000)
        assert report.summary["monthly_revenue"] == 500000

    def test_roi_report_has_recommendations(self):
        report = self.calc.calculate_roi()
        assert len(report.recommendations) > 0

    def test_roi_report_summary(self):
        report = self.calc.calculate_roi()
        assert "active_use_cases" in report.summary
        assert "monthly_savings" in report.summary
        assert report.summary["active_use_cases"] == 7

    def test_quick_estimate(self):
        estimate = self.calc.get_quick_estimate(monthly_revenue=200000)
        assert "monthly_savings" in estimate
        assert "annual_savings" in estimate
        assert "roi_percent" in estimate
        assert "payback_months" in estimate

    def test_use_cases_have_required_keys(self):
        for key, uc in self.calc.use_cases.items():
            assert "area" in uc
            assert "description" in uc
            assert "labor_hours_saved" in uc
            assert "error_reduction" in uc
            assert "revenue_increase" in uc
            assert "monthly_cost" in uc


# ── helpers.py tests ────────────────────────────────────────


class TestDemoHelpers:
    def test_generate_demo_order(self):
        order = generate_demo_order()
        assert order["id"].startswith("ORD-")
        assert order["total"] > 0
        assert order["currency"] == "USD"
        assert "shipping_address" in order
        assert order["status"] == "pending"

    def test_generate_demo_cart(self):
        cart = generate_demo_cart()
        assert cart["id"].startswith("CART-")
        assert cart["total"] > 0
        assert len(cart["items"]) >= 1
        assert cart["currency"] == "USD"

    def test_generate_demo_ticket(self):
        ticket = generate_demo_ticket()
        assert ticket["id"].startswith("TICKET-")
        assert ticket["sentiment"] in ["positive", "neutral", "negative"]
        assert ticket["priority"] in ["low", "medium", "high", "urgent"]

    def test_generate_demo_product(self):
        product = generate_demo_product()
        assert product["id"].startswith("PROD-")
        assert product["price"] > 0
        assert product["status"] in ["active", "out_of_stock"]

    def test_generate_demo_analytics(self):
        analytics = generate_demo_analytics()
        assert "revenue" in analytics
        assert "fraud_detection" in analytics
        assert "cart_recovery" in analytics
        assert "customer_support" in analytics
        assert analytics["revenue"]["total"] > 0
