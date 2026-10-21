"""
OpsIQ Marketing & Ad-Spend Guardian Engine.
Automates inventory-to-ad synchronization, pausing paid ads on out-of-stock bestsellers
to prevent wasted advertising spend and protect net profit margins.
"""

from ecommerce_ops.marketing.ad_spend_guardian import AdSpendGuardian

__all__ = ["AdSpendGuardian"]
