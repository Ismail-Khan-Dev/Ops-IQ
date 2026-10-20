"""
Response Generation Engine
Generates AI-powered customer support responses.
"""

import logging
from typing import Any, ClassVar, Dict, List, Optional

from ecommerce_ops.agents.customer_support.models import (
    KnowledgeArticle,
    ResponseSuggestion,
    SentimentType,
    SupportTicket,
    TicketCategory,
    TicketPriority,
)

logger = logging.getLogger("ecommerce_ops.agents.customer_support.response")


class ResponseTemplates:
    """Built-in response templates for common scenarios."""

    TEMPLATES: ClassVar[Dict[TicketCategory, List[Dict[str, Any]]]] = {
        TicketCategory.ORDER_STATUS: [
            {
                "name": "order_status_general",
                "subject": "Re: Your Order Status - {order_id}",
                "body": """Hi {customer_name},

Thank you for reaching out about your order {order_id}.

{order_status_message}

If you have any other questions, please don't hesitate to ask.

Best regards,
{agent_name}""",
            },
        ],
        TicketCategory.SHIPPING: [
            {
                "name": "shipping_delay",
                "subject": "Re: Shipping Update - {order_id}",
                "body": """Hi {customer_name},

I understand you're concerned about your shipment.

{shipping_update}

We apologize for any inconvenience. Your satisfaction is our priority.

Best regards,
{agent_name}""",
            },
        ],
        TicketCategory.RETURNS: [
            {
                "name": "return_request",
                "subject": "Re: Return Request - {order_id}",
                "body": """Hi {customer_name},

I'd be happy to help you with your return.

{return_instructions}

Please let me know if you need any assistance.

Best regards,
{agent_name}""",
            },
        ],
        TicketCategory.PRODUCT_QUESTION: [
            {
                "name": "product_inquiry",
                "subject": "Re: Product Information",
                "body": """Hi {customer_name},

Thank you for your interest in our products!

{product_information}

Feel free to ask if you have any other questions.

Best regards,
{agent_name}""",
            },
        ],
    }


class ResponseGenerationEngine:
    """Generates contextual support responses using AI and templates."""

    def __init__(self):
        self.templates = ResponseTemplates()
        self._knowledge_base: List[KnowledgeArticle] = []

    def generate_suggestion(
        self,
        ticket: SupportTicket,
        conversation_history: List[Dict[str, Any]] | None = None,
        customer_context: Optional[Dict[str, Any]] = None,
    ) -> ResponseSuggestion:
        """Generate a response suggestion for a ticket."""
        # Analyze sentiment
        sentiment = self._analyze_sentiment(ticket.body)
        ticket.sentiment = sentiment

        # Classify urgency
        priority = self._assess_urgency(ticket, sentiment)

        # Find relevant knowledge articles
        relevant_articles = self._find_relevant_articles(ticket)

        # Generate response based on category and context
        response = self._generate_response(
            ticket,
            sentiment,
            relevant_articles,
            customer_context,
        )

        # Determine if human review is needed
        requires_review = self._requires_human_review(ticket, sentiment, response["confidence"])

        # Generate follow-up questions
        follow_ups = self._generate_follow_ups(ticket, response)

        return ResponseSuggestion(
            ticket_id=ticket.id,
            suggested_response=response["body"],
            confidence=response["confidence"],
            reasoning=response["reasoning"],
            template_used=response.get("template_used"),
            requires_human_review=requires_review,
            follow_up_questions=follow_ups,
            estimated_resolution_time=self._estimate_resolution_time(ticket, priority),
        )

    def get_template(
        self, category: TicketCategory, template_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Get response template for a category."""
        templates = self.templates.TEMPLATES.get(category, [])
        if not templates:
            return None
        if template_name:
            for t in templates:
                if t["name"] == template_name:
                    return t
        return templates[0] if templates else None

    def personalize_response(
        self,
        template: Dict[str, Any],
        context: Dict[str, Any],
    ) -> str:
        """Personalize a template with context variables."""
        body = template["body"]
        for key, value in context.items():
            placeholder = "{" + key + "}"
            if placeholder in body:
                body = body.replace(placeholder, str(value))
        return body

    def _analyze_sentiment(self, text: str) -> SentimentType:
        """Analyze text sentiment."""
        text_lower = text.lower()

        # Strong negative indicators
        negative_strong = ["angry", "furious", "terrible", "horrible", "worst", "unacceptable"]
        # Negative indicators
        negative = ["disappointed", "frustrated", "upset", "annoyed", "problem", "issue", "wrong"]
        # Positive indicators
        positive = ["happy", "great", "excellent", "love", "thank", "appreciate", "wonderful"]
        # Strong positive
        positive_strong = ["amazing", "fantastic", "perfect", "outstanding", "exceptional"]

        score = 0

        for word in negative_strong:
            if word in text_lower:
                score -= 2
        for word in negative:
            if word in text_lower:
                score -= 1
        for word in positive:
            if word in text_lower:
                score += 1
        for word in positive_strong:
            if word in text_lower:
                score += 2

        # Check for urgency markers
        urgency_words = ["urgent", "asap", "immediately", "emergency", "critical"]
        for word in urgency_words:
            if word in text_lower:
                score -= 1

        if score <= -3:
            return SentimentType.VERY_NEGATIVE
        elif score <= -1:
            return SentimentType.NEGATIVE
        elif score == 0:
            return SentimentType.NEUTRAL
        elif score <= 2:
            return SentimentType.POSITIVE
        else:
            return SentimentType.VERY_POSITIVE

    def _assess_urgency(self, ticket: SupportTicket, sentiment: SentimentType) -> TicketPriority:
        """Assess ticket urgency based on content and sentiment."""
        text_lower = ticket.body.lower()

        # Critical indicators
        critical_words = ["lawsuit", "legal", "attorney", "media", "social media", "viral"]
        for word in critical_words:
            if word in text_lower:
                return TicketPriority.CRITICAL

        # Urgent indicators
        urgent_words = ["refund", "missing", "wrong", "damaged", "broken", "never received"]
        for word in urgent_words:
            if word in text_lower:
                return TicketPriority.URGENT

        # High priority
        if sentiment in (SentimentType.VERY_NEGATIVE, SentimentType.NEGATIVE):
            return TicketPriority.HIGH

        # Check customer history (if available)
        if ticket.metadata.get("is_vip_customer"):
            return TicketPriority.HIGH

        if ticket.metadata.get("total_orders", 0) > 10:
            return TicketPriority.HIGH

        return TicketPriority.NORMAL

    def _find_relevant_articles(self, ticket: SupportTicket) -> List[KnowledgeArticle]:
        """Find relevant knowledge base articles."""
        relevant = []

        for article in self._knowledge_base:
            if not article.is_published:
                continue

            # Check category match
            if article.category == ticket.category:
                relevant.append(article)
                continue

            # Check keyword overlap
            ticket_words = set(ticket.body.lower().split())
            article_words = set(article.title.lower().split() + article.content.lower().split())

            overlap = len(ticket_words & article_words)
            if overlap >= 3:
                relevant.append(article)

        # Sort by helpfulness
        relevant.sort(key=lambda a: a.helpfulness_ratio, reverse=True)
        return relevant[:3]

    def _generate_response(
        self,
        ticket: SupportTicket,
        sentiment: SentimentType,
        relevant_articles: List[KnowledgeArticle],
        customer_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Generate response body with confidence score."""
        # Get appropriate template
        template = self.get_template(ticket.category)

        if template:
            # Personalize template
            context = {
                "customer_name": ticket.customer_name or "there",
                "order_id": ticket.order_id or "N/A",
                "agent_name": "Support Team",
                "order_status_message": "Your order is being processed.",
                "shipping_update": "We're checking on your shipment status.",
                "return_instructions": "Please follow our return process at [link].",
                "product_information": "Here's the information you requested.",
            }
            if customer_context:
                context.update(customer_context)

            body = self.personalize_response(template, context)
            confidence = 0.7
            reasoning = f"Used template '{template['name']}' for {ticket.category.value} category"
        else:
            # Generate custom response
            body = self._generate_custom_response(ticket, sentiment, relevant_articles)
            confidence = 0.5
            reasoning = "Generated custom response based on ticket content"

        # Adjust confidence based on factors
        if relevant_articles:
            confidence += 0.1
            reasoning += f". Found {len(relevant_articles)} relevant knowledge articles"

        if sentiment in (SentimentType.VERY_NEGATIVE, SentimentType.NEGATIVE):
            confidence -= 0.1
            reasoning += ". Negative sentiment detected - may need personal touch"

        return {
            "body": body,
            "confidence": min(max(confidence, 0.0), 1.0),
            "reasoning": reasoning,
            "template_used": template["name"] if template else None,
        }

    def _generate_custom_response(
        self,
        ticket: SupportTicket,
        sentiment: SentimentType,
        articles: List[KnowledgeArticle],
    ) -> str:
        """Generate a custom response when no template matches."""
        greeting = f"Hi {ticket.customer_name}," if ticket.customer_name else "Hi there,"

        # Acknowledge sentiment
        if sentiment in (SentimentType.VERY_NEGATIVE, SentimentType.NEGATIVE):
            acknowledgment = "I'm sorry to hear about your experience. I understand your frustration and I'm here to help."
        elif sentiment == SentimentType.NEUTRAL:
            acknowledgment = "Thank you for reaching out to us."
        else:
            acknowledgment = "Thank you for contacting us!"

        # Main response based on category
        category_responses = {
            TicketCategory.ORDER_STATUS: "Let me look into your order status right away.",
            TicketCategory.SHIPPING: "I'll check on your shipping status immediately.",
            TicketCategory.RETURNS: "I'd be happy to assist you with your return.",
            TicketCategory.REFUNDS: "Let me look into your refund request.",
            TicketCategory.PRODUCT_QUESTION: "I'd be happy to answer your product questions.",
            TicketCategory.COMPLAINT: "I sincerely apologize for the inconvenience. Let me resolve this for you.",
            TicketCategory.TECHNICAL: "I'll help you troubleshoot this technical issue.",
            TicketCategory.ACCOUNT: "I'll assist you with your account right away.",
            TicketCategory.BILLING: "Let me review your billing concern.",
            TicketCategory.OTHER: "How can I assist you today?",
        }
        main_response = category_responses.get(ticket.category, "I'm here to help.")

        # Add article references
        article_text = ""
        if articles:
            article_text = "\n\nHere are some helpful resources:\n"
            for article in articles[:2]:
                article_text += f"- {article.title}\n"

        closing = "\n\nPlease let me know if you need anything else. We're here to help!"

        return f"{greeting}\n\n{acknowledgment}\n\n{main_response}{article_text}{closing}"

    def _requires_human_review(
        self,
        ticket: SupportTicket,
        sentiment: SentimentType,
        confidence: float,
    ) -> bool:
        """Determine if response needs human review."""
        # Always escalate critical tickets
        if ticket.priority == TicketPriority.CRITICAL:
            return True

        # Escalate very negative sentiment
        if sentiment == SentimentType.VERY_NEGATIVE:
            return True

        # Escalate if confidence is low
        if confidence < 0.6:
            return True

        # Escalate legal/complaint issues
        if ticket.category in (TicketCategory.COMPLAINT, TicketCategory.BILLING):
            text_lower = ticket.body.lower()
            if any(w in text_lower for w in ["legal", "attorney", "sue", "lawsuit"]):
                return True

        # Escalate VIP customers
        return bool(ticket.metadata.get("is_vip_customer"))

    def _generate_follow_ups(self, ticket: SupportTicket, response: Dict[str, Any]) -> List[str]:
        """Generate follow-up questions to gather more info."""
        follow_ups = []

        if ticket.category == TicketCategory.ORDER_STATUS and not ticket.order_id:
            follow_ups.append("Could you please provide your order number?")

        if ticket.category == TicketCategory.SHIPPING and not ticket.order_id:
            follow_ups.append("What's your order number so I can track your shipment?")

        if ticket.category == TicketCategory.RETURNS:
            follow_ups.append("What's the reason for your return?")
            follow_ups.append("When did you receive the item?")

        if ticket.category == TicketCategory.TECHNICAL:
            follow_ups.append("What device and browser are you using?")
            follow_ups.append("Can you describe the exact error you're seeing?")

        return follow_ups[:3]

    def _estimate_resolution_time(self, ticket: SupportTicket, priority: TicketPriority) -> float:
        """Estimate resolution time in hours."""
        base_times = {
            TicketPriority.LOW: 48,
            TicketPriority.NORMAL: 24,
            TicketPriority.HIGH: 8,
            TicketPriority.URGENT: 4,
            TicketPriority.CRITICAL: 1,
        }

        base = base_times.get(priority, 24)

        # Adjust by category
        category_multipliers = {
            TicketCategory.ORDER_STATUS: 0.5,
            TicketCategory.SHIPPING: 0.75,
            TicketCategory.RETURNS: 1.5,
            TicketCategory.REFUNDS: 2.0,
            TicketCategory.PRODUCT_QUESTION: 0.5,
            TicketCategory.COMPLAINT: 2.0,
            TicketCategory.TECHNICAL: 1.5,
            TicketCategory.ACCOUNT: 1.0,
            TicketCategory.BILLING: 1.5,
        }

        multiplier = category_multipliers.get(ticket.category, 1.0)
        return base * multiplier

    def load_knowledge_base(self, articles: List[KnowledgeArticle]):
        """Load knowledge base articles."""
        self._knowledge_base = articles
        logger.info("Loaded %d knowledge base articles", len(articles))
