"""
LLM-Powered Marketing Automation Agent
Uses LLM for campaign creation, audience segmentation, and content optimization.
"""

import logging
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from ecommerce_ops.agents._base import BaseAgent
from ecommerce_ops.agents.cost_tracker import track_llm_cost
from ecommerce_ops.agents.message_bus import AgentMessage, MessageTopics, message_bus
from ecommerce_ops.memory.llm_cache import llm_response_cache
from ecommerce_ops.safety.guardrails import guardrail_blocked, guardrail_manager

logger = logging.getLogger("ecommerce_ops.agents.marketing_llm")


class MarketingCampaignOutput(BaseModel):
    """Structured output for marketing campaign."""

    campaign_name: str = Field(description="Campaign name")
    campaign_type: str = Field(description="Type: email, sms, push, social, discount")
    target_audience: Dict[str, Any] = Field(description="Target audience segment")
    content: Dict[str, str] = Field(description="Campaign content (subject, body, etc)")
    estimated_reach: int = Field(description="Estimated audience size")
    estimated_ctr: float = Field(description="Estimated click-through rate")
    estimated_revenue: float = Field(description="Estimated revenue impact")
    reasoning: str = Field(description="Campaign reasoning")
    ab_test_variants: List[Dict[str, Any]] = Field(description="A/B test variants")


MARKETING_SYSTEM_PROMPT = """You are an expert marketing automation AI for an e-commerce platform.

Your role is to create effective marketing campaigns that drive revenue while respecting customer preferences.

Campaign Types:
1. EMAIL - Email campaigns with personalized content
2. SMS - Text message campaigns for urgent offers
3. PUSH - Push notifications for app users
4. DISCOUNT - Discount and promotion campaigns
5. SOCIAL - Social media campaigns
6. RETARGETING - Re-engage abandoned carts/browsers

Audience Segmentation:
- VIP customers (top 10% by spend)
- High-value customers (regular buyers)
- At-risk customers (declining engagement)
- New customers (first 30 days)
- Lapsed customers (no purchase in 60+ days)
- Cart abandoners (left items in cart)
- Product-specific interest groups

Content Best Practices:
- Personalize with customer name and preferences
- Create urgency without being pushy
- Clear call-to-action
- Mobile-optimized content
- A/B test subject lines and offers

IMPORTANT:
- Respect customer communication preferences
- Follow CAN-SPAM and GDPR guidelines
- Don't over-communicate (max 2 emails/week)
- Track campaign performance for optimization
- Never send misleading or deceptive content
"""


class MarketingAutomationAgentLLM(BaseAgent):
    """LLM-powered marketing automation agent."""

    def __init__(self):
        super().__init__(agent_name="marketing_automation")
        self.message_bus = message_bus
        self.message_bus.subscribe_agent("marketing_automation", self._handle_message)

    async def _handle_message(self, message: AgentMessage):
        """Handle messages from other agents."""
        if message.topic == MessageTopics.CART_ABANDONED:
            cart_data = message.payload
            await self.create_campaign(
                {
                    "trigger": "cart_abandonment",
                    "customer": cart_data.get("customer"),
                    "cart_value": cart_data.get("total"),
                }
            )

        elif message.topic == MessageTopics.ORDER_SHIPPED:
            order_data = message.payload
            await self.create_campaign(
                {
                    "trigger": "post_purchase",
                    "customer": order_data.get("customer"),
                    "order": order_data,
                }
            )

    async def create_campaign(self, context_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a marketing campaign using LLM."""
        context = self._build_context(context_data)

        # Guardrail
        input_check = guardrail_manager.check_input(str(context_data))
        if not input_check.passed:
            logger.warning(
                "Input guardrail blocked for MarketingAgent; quarantining for HITL review: %s",
                input_check.violations,
            )
            return guardrail_blocked(input_check.violations)

        # LLM response cache
        cached = await llm_response_cache.get(context, namespace="marketing_automation")
        if cached is not None:
            logger.info("Marketing LLM cache hit")
            return cached

        try:
            messages = [
                SystemMessage(content=MARKETING_SYSTEM_PROMPT),
                HumanMessage(content=context),
            ]

            response = await self.llm.ainvoke(messages)
            track_llm_cost(response, agent="marketing_automation")
            campaign = self._parse_response(response.content, context_data)

            # Validate output
            output_check = guardrail_manager.validate_agent_output(
                campaign,
                required_fields=[
                    "campaign_name",
                    "campaign_type",
                    "target_audience",
                    "content",
                    "reasoning",
                ],
            )
            if not output_check.passed:
                return self._rule_based_fallback(context_data)

            await llm_response_cache.set(context, campaign, namespace="marketing_automation")

            # Broadcast campaign created
            await self.message_bus.broadcast(
                sender="marketing_automation",
                payload=campaign,
                message_type="info",
                topic=MessageTopics.CAMPAIGN_CREATED,
            )

            return campaign

        except Exception as e:
            logger.error(f"LLM campaign creation failed: {e}")
            return self._rule_based_fallback(context_data)

    def _build_context(self, context_data: Dict[str, Any]) -> str:
        """Build campaign context."""
        trigger = context_data.get("trigger", "manual")
        customer = context_data.get("customer", {})

        return f"""
Create a marketing campaign based on this context:

Trigger: {trigger}
Customer Segment: {customer.get("segment", "all")}
Customer Name: {customer.get("name", "Customer")}
Customer Email: {customer.get("email", "unknown")}
Cart Value: ${context_data.get("cart_value", 0):.2f}
Last Purchase: {customer.get("last_purchase_date", "unknown")}
Purchase Frequency: {customer.get("purchase_frequency", "unknown")}
Average Order Value: ${customer.get("avg_order_value", 0):.2f}

Create an effective campaign that will drive conversions while respecting customer preferences.
Include A/B test variants for optimization.
"""

    def _parse_response(self, response: str, context_data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse LLM response."""
        try:
            import json
            import re

            json_match = re.search(r'\{[^{}]*"campaign_name"[^{}]*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())

            return {
                "campaign_name": f"Campaign_{context_data.get('trigger', 'manual')}",
                "campaign_type": "email",
                "target_audience": {"segment": "all"},
                "content": {
                    "subject": "Special offer just for you!",
                    "body": response[:500],
                },
                "estimated_reach": 1000,
                "estimated_ctr": 0.02,
                "estimated_revenue": 500,
                "reasoning": response[:500],
                "ab_test_variants": [],
            }

        except Exception as e:
            logger.error(f"Failed to parse response: {e}")
            return self._rule_based_fallback(context_data)

    def _rule_based_fallback(self, context_data: Dict[str, Any]) -> Dict[str, Any]:
        """Rule-based fallback."""
        trigger = context_data.get("trigger", "manual")

        if trigger == "cart_abandonment":
            return {
                "campaign_name": "Cart Recovery Campaign",
                "campaign_type": "email",
                "target_audience": {"segment": "cart_abandoners"},
                "content": {
                    "subject": "You left something behind!",
                    "body": "Complete your purchase and get 10% off with code SAVE10",
                },
                "estimated_reach": 500,
                "estimated_ctr": 0.05,
                "estimated_revenue": 2000,
                "reasoning": "Rule-based: Cart abandonment recovery",
                "ab_test_variants": [
                    {"subject": "Don't miss out!", "offer": "free_shipping"},
                ],
            }
        else:
            return {
                "campaign_name": "Engagement Campaign",
                "campaign_type": "email",
                "target_audience": {"segment": "active_customers"},
                "content": {
                    "subject": "Check out what's new!",
                    "body": "Discover our latest products and offers",
                },
                "estimated_reach": 1000,
                "estimated_ctr": 0.02,
                "estimated_revenue": 1000,
                "reasoning": "Rule-based: Default engagement campaign",
                "ab_test_variants": [],
            }
