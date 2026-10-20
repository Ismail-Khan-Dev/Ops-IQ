"""
Margin Preservation Calculator & Return Unit Economics Engine
Core financial intelligence module for US DTC Shopify brands ($1M-$10M GMV).

Calculates exact unit economics on returns, exchanges, and out-of-stock substitutions:
  - Reverse carrier shipping avoidance (USPS/UPS return labels)
  - 3PL warehouse receiving, inspection, and restocking fee avoidance
  - Product depreciation & markdown salvage loss prevention
  - Preserved Gross Merchandise Value (GMV) and Net Margin ROI
"""

import logging
from typing import Any, Dict, List, Optional

from ecommerce_ops.models import ApprovalAction
from ecommerce_ops.utils import utc_now

logger = logging.getLogger("ecommerce_ops.analytics.margin_preservation")

# Benchmark operational costs for US DTC brands ($1M-$10M GMV)
DEFAULT_BENCHMARKS = {
    "reverse_shipping_label_usd": 8.50,       # Average USPS Priority / UPS Ground prepaid return label
    "warehouse_restock_fee_usd": 3.75,        # 3PL intake scan, inspection, polybagging & bin return
    "warehouse_inspection_fee_usd": 2.25,     # Manual inspection for damage / tags
    "customer_support_overhead_usd": 4.50,    # Customer service handling time per return ticket
    "default_cogs_ratio": 0.28,               # 28% COGS (72% gross margin industry standard)
    "category_depreciation_rates": {
        "apparel": 0.35,                      # 35% salvage loss (opened packaging, worn, unsellable at full MSRP)
        "clothing": 0.35,
        "shoes": 0.25,                        # 25% salvage loss (box damage)
        "footwear": 0.25,
        "beauty": 0.85,                       # 85% salvage loss (opened hygiene products cannot be resold)
        "skincare": 0.85,
        "cosmetics": 0.85,
        "home": 0.20,
        "accessories": 0.15,
        "electronics": 0.30,
        "default": 0.30,
    },
}


class MarginPreservationCalculator:
    """Financial calculation engine for e-commerce return avoidance and order swaps."""

    def __init__(self, benchmarks: Optional[Dict[str, Any]] = None):
        self.benchmarks = {**DEFAULT_BENCHMARKS, **(benchmarks or {})}

    def get_category_depreciation_rate(self, category: Optional[str] = None) -> float:
        cat_lower = (category or "").strip().lower()
        rates = self.benchmarks["category_depreciation_rates"]
        for key, rate in rates.items():
            if key in cat_lower:
                return rate
        return rates["default"]

    def evaluate_return_unit_economics(
        self,
        item_price: float,
        cogs: Optional[float] = None,
        category: str = "apparel",
        return_reason: str = "sizing_fit",
        customer_is_vip: bool = False,
    ) -> Dict[str, Any]:
        """Calculate unit economics of a return and recommend the optimal margin-preserving strategy.

        Strategies:
          1. 'keep_it_credit': Let customer keep item; issue 100% store credit or gift card.
          2. 'instant_exchange': Swap to target size/variant immediately, preserving GMV.
          3. 'standard_return': Physical return with prepaid shipping label.
        """
        item_price = max(float(item_price), 0.0)
        if cogs is None or cogs <= 0:
            cogs = round(item_price * self.benchmarks["default_cogs_ratio"], 2)

        depreciation_rate = self.get_category_depreciation_rate(category)
        depreciation_loss = round(item_price * depreciation_rate, 2)
        shipping_cost = self.benchmarks["reverse_shipping_label_usd"]
        restock_cost = self.benchmarks["warehouse_restock_fee_usd"]
        inspection_cost = self.benchmarks["warehouse_inspection_fee_usd"]
        cs_overhead = self.benchmarks["customer_support_overhead_usd"]

        # Total cost the merchant pays to process the physical return
        total_physical_return_cost = round(
            shipping_cost + restock_cost + inspection_cost + cs_overhead + depreciation_loss,
            2,
        )

        # Baseline loss if standard refund is granted:
        # Merchant refunds item_price + pays total_physical_return_cost - salvaged_value
        salvaged_value = max(round(item_price - depreciation_loss, 2), 0.0)
        net_loss_standard_return = round(
            item_price + shipping_cost + restock_cost + inspection_cost - salvaged_value,
            2,
        )

        # Decision Matrix:
        # Case A: Low-cost or high-depreciation item where return cost exceeds salvage value
        # If total_physical_return_cost >= item_price * 0.55 or category in (beauty, skincare)
        is_beauty = any(b in category.lower() for b in ("beauty", "skincare", "cosmetic"))
        return_cost_ratio = total_physical_return_cost / max(item_price, 1.0)

        if is_beauty or (item_price <= 45.0 and return_cost_ratio >= 0.45):
            strategy = "keep_it_credit"
            # Preserved Margin = Avoided reverse shipping + avoided 3PL restock + avoided inspection
            avoided_reverse_costs = round(shipping_cost + restock_cost + inspection_cost, 2)
            # Retaining the customer with store credit preserves cash in business
            preserved_margin = avoided_reverse_costs
            recommendation_reason = (
                f"Physical return cost (${total_physical_return_cost:.2f}) represents {return_cost_ratio:.0%} of item price. "
                f"Offering 'Keep-It + Store Credit' saves ${avoided_reverse_costs:.2f} in reverse logistics fees."
            )
        elif return_reason in ("sizing_fit", "wrong_size", "too_small", "too_large", "color"):
            strategy = "instant_exchange"
            # Retains 100% of GMV and avoids cash refund
            preserved_margin = round(item_price - cogs, 2)  # Full gross profit preserved
            avoided_reverse_costs = round(cs_overhead + (restock_cost * 0.5), 2)
            recommendation_reason = (
                f"Return reason is '{return_reason}'. Offering instant variant exchange preserves "
                f"${item_price:.2f} in gross revenue and avoids full cash refund."
            )
        else:
            strategy = "standard_return"
            preserved_margin = 0.0
            avoided_reverse_costs = 0.0
            recommendation_reason = (
                f"High-ticket item (${item_price:.2f}) with salvageable condition; standard return label recommended."
            )

        return {
            "strategy": strategy,
            "item_price": item_price,
            "cogs": cogs,
            "category": category,
            "depreciation_loss": depreciation_loss,
            "reverse_shipping_cost": shipping_cost,
            "warehouse_processing_cost": round(restock_cost + inspection_cost, 2),
            "total_physical_return_cost": total_physical_return_cost,
            "avoided_reverse_costs": avoided_reverse_costs,
            "preserved_margin": preserved_margin,
            "recommendation_reason": recommendation_reason,
            "calculated_at": utc_now().isoformat(),
        }

    def evaluate_order_swap_unit_economics(
        self,
        original_price: float,
        swap_price: float,
        original_cogs: Optional[float] = None,
        swap_cogs: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Calculate margin preservation when swapping an out-of-stock item."""
        orig_price = max(float(original_price), 0.0)
        new_price = max(float(swap_price), 0.0)

        default_ratio = self.benchmarks["default_cogs_ratio"]
        if original_cogs is None or original_cogs <= 0:
            original_cogs = round(orig_price * default_ratio, 2)
        if swap_cogs is None or swap_cogs <= 0:
            swap_cogs = round(new_price * default_ratio, 2)

        original_margin = round(orig_price - original_cogs, 2)
        swap_margin = round(new_price - swap_cogs, 2)
        margin_delta = round(swap_margin - original_margin, 2)

        # Without swap, customer cancels -> $0 GMV, $0 margin
        # With swap, entire swap_price GMV and swap_margin profit are preserved!
        preserved_gmv = new_price
        preserved_net_margin = swap_margin

        return {
            "original_price": orig_price,
            "swap_price": new_price,
            "original_cogs": original_cogs,
            "swap_cogs": swap_cogs,
            "original_margin": original_margin,
            "swap_margin": swap_margin,
            "margin_delta": margin_delta,
            "preserved_gmv": preserved_gmv,
            "preserved_net_margin": preserved_net_margin,
            "explanation": (
                f"Swap preserves ${preserved_gmv:.2f} GMV and ${preserved_net_margin:.2f} net margin "
                f"(margin delta: {margin_delta:+.2f} vs original)."
            ),
        }

    @staticmethod
    def aggregate_margin_metrics(actions: List[ApprovalAction]) -> Dict[str, Any]:
        """Aggregate total margin, GMV, and logistics savings from executed actions."""
        total_gmv_preserved = 0.0
        total_reverse_logistics_saved = 0.0
        total_net_margin_preserved = 0.0
        by_strategy_counts: Dict[str, int] = {
            "keep_it_credit": 0,
            "instant_exchange": 0,
            "order_swap": 0,
            "fraud_prevention": 0,
            "cart_recovery": 0,
        }

        for act in actions:
            if act.status not in ("executed", "approved"):
                continue

            impact = act.impact or {}
            fin_impact = float(impact.get("financial_impact", 0.0))
            pres_margin = float(impact.get("preserved_margin", 0.0))
            rev_saved = float(impact.get("reverse_costs_saved", 0.0))
            strategy = impact.get("strategy") or act.action_type

            if act.action_type == "order_swap":
                total_gmv_preserved += float(impact.get("preserved_gmv", fin_impact))
                total_net_margin_preserved += pres_margin or fin_impact
                by_strategy_counts["order_swap"] += 1
            elif act.action_type == "return_risk_flag":
                total_reverse_logistics_saved += rev_saved
                total_net_margin_preserved += pres_margin
                if "keep" in str(strategy).lower():
                    by_strategy_counts["keep_it_credit"] += 1
                elif "exchange" in str(strategy).lower():
                    by_strategy_counts["instant_exchange"] += 1
            elif act.action_type == "fraud_hold":
                total_gmv_preserved += fin_impact
                total_net_margin_preserved += fin_impact
                by_strategy_counts["fraud_prevention"] += 1
            elif act.action_type == "cart_recovery":
                total_gmv_preserved += fin_impact
                total_net_margin_preserved += round(fin_impact * 0.70, 2)
                by_strategy_counts["cart_recovery"] += 1

        # Annualized run-rate projection (assuming monthly baseline)
        annualized_savings = round((total_net_margin_preserved + total_reverse_logistics_saved) * 12, 2)
        # Software ROI multiple (assuming $999/mo standard plan)
        monthly_total_saved = max(total_net_margin_preserved + total_reverse_logistics_saved, 1.0)
        roi_multiple = round(monthly_total_saved / 999.0, 1)

        return {
            "total_gmv_preserved_usd": round(total_gmv_preserved, 2),
            "reverse_logistics_saved_usd": round(total_reverse_logistics_saved, 2),
            "total_net_margin_preserved_usd": round(total_net_margin_preserved, 2),
            "total_value_delivered_usd": round(total_net_margin_preserved + total_reverse_logistics_saved, 2),
            "annualized_projected_savings_usd": annualized_savings,
            "estimated_software_roi_multiple": f"{roi_multiple}x",
            "strategy_breakdown": by_strategy_counts,
            "actions_analyzed": len(actions),
        }
