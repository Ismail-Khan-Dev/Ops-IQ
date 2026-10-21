"""
OpsIQ High-ROI Returns Innovation Suite.
Includes:
- Wardrobing & Bracketing Anti-Abuse Shield
- Post-Purchase Up-Exchange AI Negotiation Engine
- Live Margin Preserved Counter & Shopify Admin Widget
"""

from ecommerce_ops.returns.live_margin_widget import LiveMarginWidget
from ecommerce_ops.returns.up_exchange import UpExchangeEngine
from ecommerce_ops.returns.wardrobing_shield import WardrobingShield

__all__ = ["WardrobingShield", "UpExchangeEngine", "LiveMarginWidget"]
